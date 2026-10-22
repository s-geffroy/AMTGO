"""Moteur de mesure (07 §8) : observations + support + vraisemblance + qualité → champ latent.

Sélection explicite des observations, chaque exclusion étant comptée avec sa
raison (jamais silencieuse) :
- la source et la variable doivent être déclarées par une vraisemblance ;
- le rôle ``population_measurement`` doit être déclaré pour la source dans le run ;
- portes de qualité dimension par dimension ;
- **temporalité** : l'intervalle de validité doit recouper la période cible.
  Aucune harmonisation temporelle n'existe encore : une observation hors période
  est exclue, pas « ajustée » (03 §29).
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, time

import numpy as np

from amtgo.data.observations import Observation
from amtgo.errors import InsufficientEvidence
from amtgo.geo.mesh import Mesh
from amtgo.measurement.fusion import (
    GaussianPrior,
    LaplaceInfo,
    LogNormalPrior,
    Posterior,
    fuse,
    fuse_lognormal,
    rake_to_margins,
)
from amtgo.measurement.likelihoods import DesignRow, MeshIndex, design_row
from amtgo.measurement.manifest import (
    GaussianDensityPrior,
    LikelihoodSpec,
    MeasurementManifest,
    ObservationUse,
    RasterLogNormalDensityPrior,
)

ROLE_MEASUREMENT = "population_measurement"


@dataclass
class Selection:
    rows: list[DesignRow]
    used: Counter[str] = field(default_factory=Counter)  # par source (slug)
    excluded: Counter[str] = field(default_factory=Counter)  # par raison

    def subset(self, keep: set[str]) -> list[DesignRow]:
        return [r for r in self.rows if r.source_id in keep]


def prior_for(mesh_index: MeshIndex, manifest: MeasurementManifest,
              prior_density: np.ndarray | None = None) -> GaussianPrior | LogNormalPrior:
    """``prior_density`` : densité médiane par cellule, lue sur le raster (prior raster uniquement)."""
    p = manifest.prior
    if isinstance(p, RasterLogNormalDensityPrior):
        if prior_density is None or len(prior_density) != len(mesh_index):
            raise InsufficientEvidence("prior raster : densités par cellule absentes ou d'un autre maillage")
        return LogNormalPrior(log_mean=np.log(prior_density), log_var=np.full(len(mesh_index), p.log_sd**2),
                              area=mesh_index.area)
    if isinstance(p, GaussianDensityPrior):
        return GaussianPrior(mean=p.density_mean_per_km2 * mesh_index.area,
                             var=(p.density_sd_per_km2 * mesh_index.area) ** 2)
    n = len(mesh_index)
    return LogNormalPrior(log_mean=np.full(n, np.log(p.median_density_per_km2)),
                          log_var=np.full(n, p.log_sd**2), area=mesh_index.area)


def _in_period(obs: Observation, manifest: MeasurementManifest) -> bool:
    start = datetime.combine(manifest.target_period.start, time.min, tzinfo=UTC)
    end = datetime.combine(manifest.target_period.end, time.max, tzinfo=UTC)
    until = obs.valid_until or obs.valid_from
    return obs.valid_from <= end and until >= start


def select_observations(
    observations: list[Observation],
    manifest: MeasurementManifest,
    mesh_index: MeshIndex,
    source_uuid_to_slug: dict[str, str],
    measurement_sources: set[str],
) -> Selection:
    """``measurement_sources`` : slugs des sources déclarées avec le rôle de mesure dans le run."""
    specs: dict[tuple[str, str], LikelihoodSpec] = {
        (lk.source_id, lk.variable_id): lk for lk in manifest.likelihoods
    }
    gates = manifest.quality_gates
    sel = Selection(rows=[])
    for obs in sorted(observations, key=lambda o: str(o.id)):
        slug = source_uuid_to_slug.get(obs.source_id, "?")
        spec = specs.get((slug, obs.variable_id))
        if spec is None:
            sel.excluded["no_likelihood"] += 1
            continue
        if slug not in measurement_sources:
            sel.excluded["role_not_declared"] += 1
            continue
        q = obs.quality
        if (q.construct_validity < gates.min_construct_validity
                or q.privacy_usability < gates.min_privacy_usability
                or q.license_usability < gates.min_license_usability):
            sel.excluded["quality_gate"] += 1
            continue
        if not _in_period(obs, manifest):
            sel.excluded["temporal_mismatch"] += 1
            continue
        # Les lignes portent l'identifiant lisible de la source (slug), utilisé par l'ablation.
        row = dataclasses.replace(design_row(obs, spec, mesh_index), source_id=slug)
        if len(row.cells) == 0:
            sel.excluded["outside_domain"] += 1
            continue
        sel.rows.append(row)
        sel.used[slug] += 1
    return sel


def is_holdout(observation_id: str, fraction: float) -> bool:
    """Tirage déterministe par empreinte : même observation → même décision, sur toute machine."""
    h = int(hashlib.sha256(observation_id.encode()).hexdigest()[:8], 16)
    return (h / 0xFFFFFFFF) < fraction


@dataclass(frozen=True)
class Prepared:
    """Index du maillage et sélection, calculés une fois et réutilisés par chaque réajustement."""

    index: MeshIndex
    selection: Selection
    manifest: MeasurementManifest
    prior_density: np.ndarray | None = None


@dataclass(frozen=True)
class FitResult:
    posterior: Posterior
    selection: Selection
    index: MeshIndex
    laplace: LaplaceInfo | None = None  # None : modèle linéaire exact


def prepare(mesh: Mesh, observations: list[Observation], manifest: MeasurementManifest,
            source_uuid_to_slug: dict[str, str], measurement_sources: set[str],
            prior_density: np.ndarray | None = None) -> Prepared:
    idx = MeshIndex(mesh)
    sel = select_observations(observations, manifest, idx, source_uuid_to_slug, measurement_sources)
    return Prepared(idx, sel, manifest, prior_density)


def fit_prepared(prep: Prepared, keep_sources: set[str] | None = None,
                 exclude_ids: set[str] | None = None) -> FitResult:
    rows = prep.selection.rows
    if keep_sources is not None:
        rows = prep.selection.subset(keep_sources)
    if exclude_ids:
        rows = [r for r in rows if r.observation_id not in exclude_ids]
    s = prep.manifest.sampling
    prior = prior_for(prep.index, prep.manifest, prep.prior_density)
    margin_sources = {lk.source_id for lk in prep.manifest.likelihoods if lk.use is ObservationUse.MARGIN}
    margins = [r for r in rows if r.source_id in margin_sources]
    rows = [r for r in rows if r.source_id not in margin_sources]
    if isinstance(prior, LogNormalPrior):
        post, info = fuse_lognormal(prior, rows, s.n_samples, s.seed)
        if margins:
            post = rake_to_margins(post, margins, s.seed, prior.log_var)
        return FitResult(post, prep.selection, prep.index, info)
    return FitResult(fuse(prior, rows, s.n_samples, s.seed), prep.selection, prep.index)


def fit(mesh: Mesh, observations: list[Observation], manifest: MeasurementManifest,
        source_uuid_to_slug: dict[str, str], measurement_sources: set[str],
        prior_density: np.ndarray | None = None) -> FitResult:
    return fit_prepared(prepare(mesh, observations, manifest, source_uuid_to_slug, measurement_sources,
                                prior_density))


def require_observations(sel: Selection) -> None:
    if not sel.rows:
        raise InsufficientEvidence(
            f"aucune observation admissible (exclusions : {dict(sel.excluded)}) : champ = prior"
        )


def summarize(samples: np.ndarray, level: float) -> tuple[float, float, float, float]:
    alpha = (1.0 - level) / 2.0
    return (float(samples.mean()), float(samples.std(ddof=1)),
            float(np.quantile(samples, alpha)), float(np.quantile(samples, 1 - alpha)))
