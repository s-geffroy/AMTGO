"""Validation de la mesure (05 §4) : calibration, prédictive, ablation, désaccord, MAUP.

- **holdout prédictif** : une fraction déterministe des observations est retirée,
  le modèle réajusté, et l'on vérifie la couverture des intervalles prédictifs ;
- **ablation de sources** : un ajustement par source seule ;
- **désaccord inter-sources** : chaque source est prédite par les autres ;
  résidus standardisés ;
- **calibration contre la vérité** : *uniquement* pour un monde synthétique dont
  toutes les sources partagent la même vérité. Pour des données réelles, la
  vérité n'existe pas et cette validation est déclarée non disponible ;
- **comparaison entre maillages** : totaux de districts reconstruits depuis chaque
  maillage ; écarts standardisés (MAUP au niveau de la mesure, prompt §16).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from statistics import NormalDist
from typing import Any

import numpy as np
import shapely
from shapely.strtree import STRtree

from amtgo.data.observations import Observation
from amtgo.data.sources import RetrievalKind, SourceManifest
from amtgo.data.synthetic_world import SyntheticWorld
from amtgo.errors import InsufficientEvidence
from amtgo.geo.crs import to_equal_area
from amtgo.geo.mesh import Mesh
from amtgo.measurement.engine import FitResult, Prepared, fit_prepared, is_holdout, prepare
from amtgo.measurement.fusion import predictive
from amtgo.measurement.likelihoods import MeshIndex
from amtgo.measurement.manifest import LogNormalDensityPrior, MeasurementManifest, RasterLogNormalDensityPrior


def _z(level: float) -> float:
    return NormalDist().inv_cdf(0.5 + level / 2.0)


@dataclass(frozen=True)
class FitContext:
    prepared: Prepared

    @cached_property
    def full(self) -> FitResult:
        """Ajustement complet, calculé une fois et partagé par les contrôles."""
        return fit_prepared(self.prepared)

    @property
    def manifest(self) -> MeasurementManifest:
        return self.prepared.manifest

    @classmethod
    def build(cls, mesh: Mesh, observations: list[Observation], manifest: MeasurementManifest,
              uuid_to_slug: dict[str, str], measurement_sources: set[str],
              prior_density: np.ndarray | None = None) -> FitContext:
        return cls(prepare(mesh, observations, manifest, uuid_to_slug, measurement_sources, prior_density))


def holdout_check(ctx: FitContext) -> dict[str, Any]:
    full = ctx.full
    frac = ctx.manifest.validation.holdout_fraction
    held = {r.observation_id for r in full.selection.rows if is_holdout(r.observation_id, frac)}
    if not held:
        return {"status": "not_available", "reason": "aucune observation tirée en holdout"}
    train = fit_prepared(ctx.prepared, exclude_ids=held)
    test_rows = [r for r in full.selection.rows if r.observation_id in held]
    mu, var = predictive(train.posterior, test_rows)
    y = np.array([r.y for r in test_rows])
    zres = (y - mu) / np.sqrt(var)
    level = ctx.manifest.sampling.interval_level
    return {"status": "done", "n_holdout": len(test_rows), "level": level,
            "coverage": float(np.mean(np.abs(zres) <= _z(level))),
            "mean_standardized_residual": float(zres.mean()),
            "rms_standardized_residual": float(np.sqrt(np.mean(zres**2)))}


def ablation(ctx: FitContext) -> dict[str, Any]:
    level = ctx.manifest.sampling.interval_level
    out: dict[str, Any] = {}
    sources = sorted({lk.source_id for lk in ctx.manifest.likelihoods})
    for keep in [set(sources)] + [{s} for s in sources]:
        f = ctx.full if keep == set(sources) else fit_prepared(ctx.prepared, keep_sources=keep)
        tot = f.posterior.samples.sum(axis=1)
        a = (1 - level) / 2
        out["+".join(sorted(keep))] = {
            "total_mean": float(tot.mean()),
            "total_interval": [float(np.quantile(tot, a)), float(np.quantile(tot, 1 - a))],
            "median_information_ratio": float(np.median(f.posterior.information_ratio)),
            "observations": f.posterior.n_observations,
        }
    return out


def disagreement(ctx: FitContext) -> dict[str, Any]:
    """Chaque source prédite par les autres : |z| > 2 fréquents ⇒ sources incompatibles."""
    full = ctx.full
    sources = sorted({r.source_id for r in full.selection.rows})
    out: dict[str, Any] = {}
    if len(sources) < 2:
        return {"status": "not_available", "reason": "une seule source"}
    for target in sources:
        others = {s for s in sources if s != target}
        f = fit_prepared(ctx.prepared, keep_sources=others)
        rows = [r for r in full.selection.rows if r.source_id == target]
        mu, var = predictive(f.posterior, rows)
        z = (np.array([r.y for r in rows]) - mu) / np.sqrt(var)
        out[target] = {"n": len(rows), "share_abs_z_gt_2": float(np.mean(np.abs(z) > 2)),
                             "max_abs_z": float(np.max(np.abs(z))), "mean_z": float(z.mean())}
    return out


def ground_truth_world(manifests: list[SourceManifest]) -> SyntheticWorld | None:
    """La vérité n'existe que si TOUTES les sources sont synthétiques et issues du même monde."""
    from amtgo.data.adapters.synthetic import world_of

    if not manifests or any(m.retrieval.kind is not RetrievalKind.SYNTHETIC for m in manifests):
        return None
    worlds = {world_of(m).world_hash: world_of(m) for m in manifests}
    return next(iter(worlds.values())) if len(worlds) == 1 else None


def true_cell_totals(world: SyntheticWorld, idx: MeshIndex) -> np.ndarray:
    pts, da = world.quadrature
    tree = STRtree(idx.geoms)
    pt_idx, cell_idx = tree.query(shapely.points(pts), predicate="intersects")
    # Un point sur une arête partagée compte une seule fois (plus petit indice).
    first: dict[int, int] = {}
    for p, c in zip(pt_idx.tolist(), cell_idx.tolist(), strict=True):
        if p not in first or c < first[p]:
            first[p] = c
    dens = world.density(pts)
    totals = np.zeros(len(idx))
    for p, c in first.items():
        totals[c] += dens[p] * da
    return totals


def calibration(ctx: FitContext, manifests: list[SourceManifest]) -> dict[str, Any]:
    world = ground_truth_world(manifests)
    if world is None:
        return {"status": "not_available", "reason": "pas de vérité terrain (données non synthétiques)"}
    f = ctx.full
    truth = true_cell_totals(world, f.index)
    level = ctx.manifest.sampling.interval_level
    a = (1 - level) / 2
    lo = np.quantile(f.posterior.samples, a, axis=0)
    hi = np.quantile(f.posterior.samples, 1 - a, axis=0)
    covered = (truth >= lo) & (truth <= hi)
    informed = f.posterior.information_ratio >= ctx.manifest.computability.c_min
    tot = f.posterior.samples.sum(axis=1)
    t_true = float(truth.sum())
    return {
        "status": "done", "level": level,
        "cell_coverage": float(covered.mean()),
        "cell_coverage_informed": float(covered[informed].mean()) if informed.any() else None,
        "informed_cells": int(informed.sum()),
        "true_total": t_true,
        "total_covered": bool(np.quantile(tot, a) <= t_true <= np.quantile(tot, 1 - a)),
        "total_relative_error": float((tot.mean() - t_true) / t_true) if t_true else None,
    }


def aggregation_weights(idx: MeshIndex, polygons_wgs84: list[Any]) -> np.ndarray:
    """(D, N) : part de chaque cellule dans chaque polygone (densité homogène dans la cellule)."""
    w = np.zeros((len(polygons_wgs84), len(idx)))
    for d, poly in enumerate(polygons_wgs84):
        p = to_equal_area(poly)
        for k in idx.tree.query(p, predicate="intersects"):
            w[d, int(k)] = idx.geoms[int(k)].intersection(p).area / 1e6 / idx.area[int(k)]
    return w


def district_totals(samples: np.ndarray, idx: MeshIndex, polygons_wgs84: list[Any]) -> np.ndarray:
    """(S, D) : totaux de chaque polygone reconstruits depuis les tirages d'un maillage."""
    return np.asarray(samples @ aggregation_weights(idx, polygons_wgs84).T)


def prior_cell_variance(idx: MeshIndex, manifest: MeasurementManifest,
                        prior_density: np.ndarray | None = None) -> np.ndarray:
    """Variance a priori de Z par cellule, dans l'espace des comptes."""
    p = manifest.prior
    if isinstance(p, RasterLogNormalDensityPrior):
        if prior_density is None:
            raise InsufficientEvidence("prior raster : densités par cellule absentes")
        s2 = p.log_sd**2
        return np.asarray(idx.area**2 * (np.exp(s2) - 1.0) * np.exp(2 * np.log(prior_density) + s2))
    if isinstance(p, LogNormalDensityPrior):
        mu, s2 = np.log(p.median_density_per_km2), p.log_sd**2
        return np.asarray(idx.area**2 * (np.exp(s2) - 1.0) * np.exp(2 * mu + s2))
    return np.asarray((p.density_sd_per_km2 * idx.area) ** 2)


def scale_information(samples: np.ndarray, idx: MeshIndex, manifest: MeasurementManifest,
                      polygons_wgs84: list[Any], prior_density: np.ndarray | None = None) -> np.ndarray:
    """Ratio d'information des totaux de polygones : 1 − var_post(T) / var_prior(T).

    Montre *à quelle échelle* la mesure est informative : une population non
    identifiée par cellule peut l'être sur des agrégats plus larges.
    """
    w = aggregation_weights(idx, polygons_wgs84)
    prior_var = (w**2) @ prior_cell_variance(idx, manifest, prior_density)
    post_var = (samples @ w.T).var(axis=0, ddof=1)
    return np.asarray(np.clip(1.0 - post_var / np.where(prior_var > 0, prior_var, np.inf), 0.0, 1.0))


def compare_across_meshes(per_mesh: dict[str, np.ndarray]) -> dict[str, Any]:
    """Écarts standardisés des totaux de polygones entre maillages : MAUP de la mesure."""
    ids = sorted(per_mesh)
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ta, tb = per_mesh[a], per_mesh[b]
            diff = ta.mean(axis=0) - tb.mean(axis=0)
            sd = np.sqrt(ta.var(axis=0, ddof=1) + tb.var(axis=0, ddof=1))
            z = np.abs(diff) / np.where(sd > 0, sd, np.inf)
            pairs.append({"a": a, "b": b, "max_abs_z": float(z.max()) if z.size else 0.0,
                          "mean_abs_z": float(z.mean()) if z.size else 0.0})
    worst = max((float(p["max_abs_z"]) for p in pairs), default=0.0)
    return {"pairs": pairs, "max_abs_z": worst}
