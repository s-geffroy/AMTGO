"""Benchmark du modèle spatial de population (A1, ADR-0029).

Les variantes d'erreur du prior raster sont ajustées sur les mêmes marges, puis
notées sur des totaux PLUS FINS que les marges (districts), jamais utilisés par
l'ajustement. Scores, par unité :

- couverture des intervalles prédictifs à plusieurs niveaux ;
- CRPS (estimateur sur tirages), rapporté au total observé (sans unité) ;
- score logarithmique sur l'échelle log (approximation normale des tirages) ;
- PIT et résidu standardisé log.

Le bruit déclaré du total observé est ajouté aux tirages : on prédit ce que
l'institut publie, pas une vérité sans erreur.

Validation croisée spatiale : les unités sont réparties en damier de blocs LAEA.
La variante retenue sur une moitié est évaluée sur l'autre, et réciproquement.
Si les deux moitiés ne retiennent pas la même variante, la sélection est
déclarée instable : aucune variante n'est retenue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from shapely import wkt
from shapely.geometry.base import BaseGeometry

from amtgo.data.observations import Observation
from amtgo.errors import InsufficientEvidence
from amtgo.geo.crs import to_equal_area
from amtgo.measurement.engine import Prepared, fit_prepared, raster_error_prior
from amtgo.measurement.fusion import LogNormalPrior
from amtgo.measurement.likelihoods import MeshIndex
from amtgo.measurement.manifest import ErrorModel, PopulationBenchmark

# Plancher des tirages avant passage au log (personnes) : borne numérique, pas paramètre.
LOG_FLOOR = 1.0


@dataclass(frozen=True)
class Units:
    """Unités de validation : totaux observés, bruit déclaré, géométries (WGS84)."""

    codes: list[str]
    y: np.ndarray
    sd: np.ndarray
    geoms: list[BaseGeometry]

    @classmethod
    def from_observations(cls, obs: list[Observation], variable_id: str) -> Units:
        codes, y, sd, geoms = [], [], [], []
        for o in sorted(obs, key=lambda o: str(o.admin_code)):
            if o.variable_id != variable_id:
                continue
            if o.value is None or not o.geometry_wkt:
                raise InsufficientEvidence(f"benchmark : unité {o.admin_code} sans total ou sans géométrie")
            codes.append(str(o.admin_code))
            y.append(o.value.mean)
            sd.append(o.value.std or 0.0)
            geoms.append(wkt.loads(o.geometry_wkt))
        if not codes:
            raise InsufficientEvidence(f"benchmark : aucune observation {variable_id}")
        return cls(codes, np.array(y), np.array(sd), geoms)


def unit_groups(idx: MeshIndex, geoms: list[BaseGeometry]) -> np.ndarray:
    """Unité contenant le centroïde de chaque cellule (−1 : aucune)."""
    groups = np.full(len(idx), -1)
    for u, g in enumerate(geoms):
        p = to_equal_area(g)
        for k in idx.tree.query(p, predicate="intersects"):
            if groups[int(k)] < 0 and p.contains(idx.geoms[int(k)].centroid):
                groups[int(k)] = u
    return groups


def cv_folds(geoms: list[BaseGeometry], block_km: float) -> np.ndarray:
    """Damier de blocs LAEA (0/1) sur le point représentatif de chaque unité."""
    side = block_km * 1000.0
    out = []
    for g in geoms:
        p = to_equal_area(g).representative_point()
        out.append((int(np.floor(p.x / side)) + int(np.floor(p.y / side))) % 2)
    return np.array(out)


def variant_prior(idx: MeshIndex, density: np.ndarray, v: ErrorModel, groups: np.ndarray) -> LogNormalPrior:
    return raster_error_prior(idx, density, v.log_sd, v.level_sd, [(s.block_km, s.sd) for s in v.scales],
                              groups if v.unit_sd is not None else None, v.unit_sd)


def crps_samples(t: np.ndarray, y: np.ndarray) -> np.ndarray:
    """CRPS par unité depuis des tirages (S, D) : E|X − y| − ½ E|X − X'| (forme triée, exacte)."""
    s = t.shape[0]
    x = np.sort(t, axis=0)
    w = (2.0 * np.arange(1, s + 1) - s - 1.0)[:, None]
    spread = 2.0 * (w * x).sum(axis=0) / s**2
    return np.asarray(np.abs(t - y[None, :]).mean(axis=0) - 0.5 * spread)


def unit_scores(t: np.ndarray, units: Units, levels: tuple[float, ...], seed: int) -> dict[str, np.ndarray]:
    """Scores par unité ; ``t`` : tirages (S, D) des totaux prédits, sans bruit d'observation."""
    rng = np.random.default_rng([seed, 41])
    t_obs = t + rng.standard_normal(t.shape) * units.sd[None, :]
    lt = np.log(np.maximum(t_obs, LOG_FLOOR))
    m, sd = lt.mean(axis=0), np.maximum(lt.std(axis=0, ddof=1), 1e-9)
    ly = np.log(units.y)
    out: dict[str, np.ndarray] = {
        "crps_rel": crps_samples(t_obs, units.y) / units.y,
        "log_score": 0.5 * np.log(2 * np.pi * sd**2) + (ly - m) ** 2 / (2 * sd**2),
        "pit": (t_obs <= units.y[None, :]).mean(axis=0),
        "z_log": (ly - m) / sd,
        "log_error": ly - np.log(np.maximum(t_obs.mean(axis=0), LOG_FLOOR)),
    }
    for lv in levels:
        a = (1 - lv) / 2
        lo, hi = np.quantile(t_obs, a, axis=0), np.quantile(t_obs, 1 - a, axis=0)
        out[f"covered_{lv:g}"] = ((units.y >= lo) & (units.y <= hi)).astype(float)
    return out


def summarize(scores: dict[str, np.ndarray], mask: np.ndarray, levels: tuple[float, ...]) -> dict[str, Any]:
    if not mask.any():
        return {"n": 0}
    s = {k: v[mask] for k, v in scores.items()}
    return {
        "n": int(mask.sum()),
        "coverage": {f"{lv:g}": float(s[f"covered_{lv:g}"].mean()) for lv in levels},
        "crps_rel": float(s["crps_rel"].mean()),
        "log_score": float(s["log_score"].mean()),
        "rms_z_log": float(np.sqrt(np.mean(s["z_log"] ** 2))),
        "mean_z_log": float(s["z_log"].mean()),
        "median_abs_log_error": float(np.median(np.abs(s["log_error"]))),
        # Histogramme du PIT en déciles : plat si calibré, en U si surconfiant, en cloche si trop prudent.
        "pit_deciles": np.histogram(s["pit"], bins=10, range=(0.0, 1.0))[0].tolist(),
    }


def deterministic_check(idx: MeshIndex, density: np.ndarray, w: np.ndarray, units: Units,
                        margin_geoms: list[BaseGeometry], margin_y: np.ndarray) -> dict[str, Any]:
    """Erreur du raster seul aux unités, après recalage proportionnel sur les marges.

    Ordre de grandeur EMPIRIQUE de l'erreur du raster sous l'échelle des marges :
    ce que les variantes doivent couvrir, sans y être ajustées.
    """
    raw = w @ (density * idx.area)
    which = np.array([next((m for m, g in enumerate(margin_geoms)
                            if g.contains(u.representative_point())), -1) for u in units.geoms])
    ratio = np.ones(len(units.y))
    for m in range(len(margin_geoms)):
        sel = which == m
        if sel.any() and raw[sel].sum() > 0:
            ratio[sel] = margin_y[m] / raw[sel].sum()
    pred = np.maximum(raw * ratio, LOG_FLOOR)
    err = np.log(units.y) - np.log(pred)
    return {"units_without_margin": int((which < 0).sum()),
            "median_abs_log_error": float(np.median(np.abs(err))),
            "p90_abs_log_error": float(np.quantile(np.abs(err), 0.9)),
            "sd_log_error": float(err.std(ddof=1))}


def score_variant(prep: Prepared, density: np.ndarray, v: ErrorModel, units: Units, w: np.ndarray,
                  groups: np.ndarray, small: np.ndarray, spec: PopulationBenchmark) -> dict[str, Any]:
    """Ajuste une variante sur les marges et note ses prédictions aux unités ; scores par unité conservés."""
    fit = fit_prepared(prep, prior=variant_prior(prep.index, density, v, groups))
    t = fit.posterior.samples @ w.T
    sc = unit_scores(t, units, spec.levels, prep.manifest.sampling.seed)
    return {
        "variant_id": v.variant_id,
        "all": summarize(sc, np.ones(len(units.y), dtype=bool), spec.levels),
        "units_ge_min_cells": summarize(sc, ~small, spec.levels),
        "per_unit": {k: [float(x) for x in val] for k, val in sc.items()},
    }


def cross_validate(results: dict[str, dict[str, Any]], folds: np.ndarray, spec: PopulationBenchmark
                   ) -> dict[str, Any]:
    """Sélection sur une moitié, évaluation sur l'autre ; scores plus faibles = préférés."""
    key = spec.selection_score
    per_fold: list[dict[str, Any]] = []
    for f in (0, 1):
        sel, ev = folds == f, folds != f
        if not sel.any() or not ev.any():
            return {"status": "not_available", "reason": "une moitié du damier est vide"}
        ranking = sorted(results, key=lambda vid: float(np.mean(np.asarray(results[vid]["per_unit"][key])[sel])))
        kept = ranking[0]
        sc = {k: np.asarray(v) for k, v in results[kept]["per_unit"].items()}
        per_fold.append({"selection_half": f, "retained": kept, "ranking": ranking,
                         "assessment": summarize(sc, ev, spec.levels)})
    retained = per_fold[0]["retained"] if per_fold[0]["retained"] == per_fold[1]["retained"] else None
    return {"status": "done", "selection_score": key, "folds": per_fold, "retained": retained,
            "units_per_half": [int((folds == f).sum()) for f in (0, 1)]}


def gate_a1(per_mesh_cv: dict[str, dict[str, Any]], spec: PopulationBenchmark) -> dict[str, Any]:
    """Gate A1 (ADR-0029) : variante retenue stable, sur chaque maillage, sans surconfiance.

    Critères, tous requis :
    - sélection stable : les deux moitiés retiennent la même variante, sur chaque maillage ;
    - même variante retenue sur tous les maillages ;
    - sur chaque moitié d'évaluation : couverture ≥ niveau − tolérance, à chaque niveau.
    La conservation des marges est assurée par construction (recalage exact) et vérifiée ailleurs.
    """
    reasons: list[str] = []
    retained = {mid: cv.get("retained") for mid, cv in per_mesh_cv.items()}
    for mid, cv in per_mesh_cv.items():
        if cv.get("status") != "done":
            reasons.append(f"{mid} : validation croisée non disponible")
            continue
        if cv["retained"] is None:
            reasons.append(f"{mid} : sélection instable ({cv['folds'][0]['retained']} / {cv['folds'][1]['retained']})")
        for fold in cv["folds"]:
            for lv, cov in fold["assessment"]["coverage"].items():
                if cov < float(lv) - spec.max_coverage_shortfall:
                    reasons.append(f"{mid} : couverture {cov:.2f} < {lv} − {spec.max_coverage_shortfall} "
                                   f"(moitié {1 - fold['selection_half']}, variante {fold['retained']})")
    if len({r for r in retained.values()}) > 1:
        reasons.append(f"variantes retenues différentes selon le maillage : {retained}")
    return {"passed": not reasons, "reasons": reasons, "retained": retained}
