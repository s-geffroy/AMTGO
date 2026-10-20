"""Mesure de composition (M4) : parts par catégorie d'une ontologie, avec incertitude.

Ce module ne produit **que des parts** π_j ∈ Δ^K par cellule, jamais une
étiquette, une majorité ou un « groupe de la cellule » (prompt §17, §92).

Modèle (ADR-0016) : Dirichlet-multinomial à deux niveaux.
- Niveau régional (grille de mise en commun, 100 km) :
  π_R ~ Dir(α₀ + κ Σ_{k∈R} n_k)
- Niveau cellule : π_j ~ Dir(c · π_R + κ Σ_k w_kj n_k)

n_k : comptes d'auto-identification de l'EA k ; w_kj : part du noyau de
géomasquage de k dans la cellule j ; κ : fraction d'échantillon effective
(représentativité). Une cellule sans réponse retombe sur la composition de sa
région, avec une large incertitude — jamais sur une composition inventée.
Approximation déclarée : les réponses d'une cellule comptent aux deux niveaux.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.strtree import STRtree

from amtgo.core.enums import SupportType
from amtgo.data.observations import Observation
from amtgo.errors import InsufficientEvidence, OntologyMappingError
from amtgo.geo.crs import to_equal_area
from amtgo.geo.mesh import BBoxExtent, Mesh, MeshDefinition, MeshFamily
from amtgo.geo.ops import create_base_mesh
from amtgo.geo.support import KERNEL_POINTS, _disk_offsets, first_hits
from amtgo.measurement.likelihoods import MeshIndex
from amtgo.measurement.manifest import Period
from amtgo.ontology.model import IdentityDimension, Ontology
from amtgo.utils.canonical import content_hash

ROLE_COMPOSITION = "composition_measurement"
ROLE_ONTOLOGY_VALIDATION = "ontology_validation"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PoolingSpec(_Strict):
    grid_base_km: float = Field(gt=0)
    grid_level: int = Field(ge=0, le=12)
    cell_concentration: float = Field(gt=0)


class ProjectionSpec(_Strict):
    ontology: str
    crosswalk: str  # chemin relatif à configs/


class ValidationSourceSpec(_Strict):
    source_id: str
    variable_id: str


class CompositionManifest(_Strict):
    model_id: str
    version: str
    dimension: IdentityDimension
    description: str
    target_period: Period
    source_id: str
    variable_id: str
    observed_ontology: str
    prior_concentration: float = Field(gt=0)
    pooling: PoolingSpec
    effective_sample_fraction: float = Field(gt=0, le=1)
    # Poids de plan des réponses (attribut ``design_weight``), normalisés à moyenne 1 pour
    # conserver la taille d'échantillon effective. Sans eux, une enquête tirée en surface
    # estime une composition par km², pas par habitant.
    use_design_weights: bool = False
    projections: tuple[ProjectionSpec, ...] = ()
    validation_sources: tuple[ValidationSourceSpec, ...] = ()

    @model_validator(mode="after")
    def _no_self_projection(self) -> Self:
        if any(p.ontology == self.observed_ontology for p in self.projections):
            raise ValueError("projection vers l'ontologie observée elle-même")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)


@dataclass(frozen=True)
class CompositionFit:
    ontology_id: str
    categories: list[str]
    samples: np.ndarray  # (S, N, K) parts par cellule
    prior_var: np.ndarray  # (N, K)
    respondents: np.ndarray  # (N,) réponses effectives (avant κ) attribuées à la cellule
    used: int
    excluded: dict[str, int]

    @property
    def information_ratio(self) -> np.ndarray:
        post = self.samples.var(axis=0, ddof=1)  # (N, K)
        return np.asarray(np.clip(1.0 - post.mean(axis=1) / self.prior_var.mean(axis=1), 0.0, 1.0))


def _in_period(obs: Observation, period: Period) -> bool:
    until = (obs.valid_until or obs.valid_from).date()
    return obs.valid_from.date() <= period.end and until >= period.start


def pooling_mesh(mesh: Mesh, spec: PoolingSpec) -> Mesh:
    minx, miny, maxx, maxy = mesh.extent.bounds
    d = MeshDefinition(mesh_id="pooling_grid", family=MeshFamily.GRID_LAEA, resolution=spec.grid_level,
                       grid_base_km=spec.grid_base_km, extent=BBoxExtent(bbox=(minx, miny, maxx, maxy)))
    return create_base_mesh(d, mesh.extent)


def fit_composition(mesh: Mesh, observations: list[Observation], manifest: CompositionManifest,
                    ontology: Ontology, source_uuid: str, n_samples: int, seed: int) -> CompositionFit:
    if ontology.ontology_id != manifest.observed_ontology:
        raise OntologyMappingError("ontologie observée ≠ ontologie du modèle")
    if ontology.dimension is not manifest.dimension:
        raise OntologyMappingError(f"dimension {ontology.dimension.value} ≠ {manifest.dimension.value}")
    cats = ontology.leaf_ids
    idx = MeshIndex(mesh)
    pool = pooling_mesh(mesh, manifest.pooling)
    pool_geoms = [to_equal_area(c.geometry) for c in pool.cells.values()]
    pool_tree = STRtree(pool_geoms)
    # Région de chaque cellule : celle qui contient son centre.
    centres = np.array([[g.centroid.x, g.centroid.y] for g in idx.geoms])
    region_of = first_hits(pool_tree, centres)
    n, k, r = len(idx), len(cats), len(pool_geoms)

    cell_counts = np.zeros((n, k))
    region_counts = np.zeros((r, k))
    excluded: dict[str, int] = {}
    used = 0
    candidates = [o for o in observations
                  if o.source_id == source_uuid and o.variable_id == manifest.variable_id]
    mean_weight = 1.0
    if manifest.use_design_weights:
        raw = [o.attributes.get("design_weight") for o in candidates]
        if any(w is None or float(w) < 0 for w in raw):
            raise InsufficientEvidence("use_design_weights : poids de plan manquants ou négatifs")
        weights = [float(w) for w in raw if w is not None]
        mean_weight = float(np.mean(weights)) if weights else 1.0
        if mean_weight <= 0:
            raise InsufficientEvidence("poids de plan tous nuls")
    for obs in sorted(observations, key=lambda o: str(o.id)):
        if obs.source_id != source_uuid or obs.variable_id != manifest.variable_id:
            continue
        reason = None
        if obs.ontology_id != ontology.ontology_id:
            reason = "other_ontology"
        elif not _in_period(obs, manifest.target_period):
            reason = "temporal_mismatch"
        elif obs.support_type is not SupportType.UNCERTAIN_POINT or obs.displacement_km is None:
            reason = "unsupported_support"
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        counts = obs.attributes.get("counts") or {}
        unknown = set(counts) - set(cats)
        if unknown:
            raise OntologyMappingError(f"{obs.id} : catégories hors ontologie {sorted(unknown)}")
        vec = np.array([float(counts.get(c, 0)) for c in cats])
        if manifest.use_design_weights:
            vec = vec * float(obs.attributes["design_weight"]) / mean_weight
        geom = obs.geometry()
        assert geom is not None and obs.displacement_km is not None
        p = to_equal_area(geom)
        pts = _disk_offsets(obs.displacement_km * 1000.0, KERNEL_POINTS) + np.array([p.x, p.y])
        cells = first_hits(idx.tree, pts)
        regions = first_hits(pool_tree, pts)
        share = 1.0 / len(pts)
        for c in cells[cells >= 0]:
            cell_counts[c] += vec * share
        for g in regions[regions >= 0]:
            region_counts[g] += vec * share
        used += 1
    if used == 0:
        raise InsufficientEvidence(f"aucune réponse admissible (exclusions : {excluded})")

    rng = np.random.default_rng([seed, 23])
    kappa = manifest.effective_sample_fraction
    a0 = manifest.prior_concentration
    region_alpha = a0 + kappa * region_counts  # (R, K)
    samples = np.zeros((n_samples, n, k))
    region_draws = np.stack([rng.dirichlet(region_alpha[g], size=n_samples) for g in range(r)], axis=1)
    c = manifest.pooling.cell_concentration
    for j in range(n):
        g = region_of[j]
        base = region_draws[:, g, :] if g >= 0 else rng.dirichlet(np.full(k, a0), size=n_samples)
        alpha = c * base + kappa * cell_counts[j][None, :]
        # Dirichlet(alpha_s) par tirage, via des Gamma indépendantes.
        gam = rng.gamma(np.maximum(alpha, 1e-12))
        samples[:, j, :] = gam / gam.sum(axis=1, keepdims=True)
    # Variance a priori marginale, sans aucune donnée : π_R ~ Dir(α₀·1), π_j | π_R ~ Dir(c·π_R).
    # Var(π_j) = (m(1−m) − V_R)/(c+1) + V_R, avec V_R = m(1−m)/(K α₀ + 1).
    m = 1.0 / k
    v_r = m * (1 - m) / (k * a0 + 1.0)
    prior_var = np.full((n, k), (m * (1 - m) - v_r) / (c + 1.0) + v_r)
    return CompositionFit(ontology.ontology_id, cats, samples, prior_var,
                          cell_counts.sum(axis=1), used, excluded)


def project(fit: CompositionFit, matrices: np.ndarray, target: Ontology) -> CompositionFit:
    """Parts sous l'ontologie cible (+ UNMAPPED), tirage par tirage."""
    from amtgo.ontology.crosswalk import apply, target_space

    s = fit.samples.shape[0]
    if matrices.shape[0] != s:
        raise ValueError("nombre de tirages incohérent entre parts et crosswalk")
    out = apply(fit.samples, matrices)
    cols = target_space(target)
    prior_var = np.full((out.shape[1], len(cols)), np.nan)
    return CompositionFit(target.ontology_id, cols, out, prior_var, fit.respondents, fit.used, fit.excluded)


def aggregate_shares(shares: np.ndarray, population: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Parts de polygones pondérées par la population : (S, D, K).

    ``shares`` (S, N, K), ``population`` (S, N), ``weights`` (D, N) parts de cellules.
    Hypothèse déclarée : population et composition indépendantes a posteriori.
    """
    mass = np.einsum("dn,sn,snk->sdk", weights, population, shares)
    tot = mass.sum(axis=2, keepdims=True)
    return np.asarray(np.divide(mass, tot, out=np.zeros_like(mass), where=tot > 0))


def effective_number(shares: np.ndarray) -> np.ndarray:
    """Nombre effectif de catégories (inverse de Simpson), descriptif : 1 / Σ π_k².

    Mesure **descriptive** de diversité. AMTGO ne pénalise jamais la diversité
    (prompt §2) : cette quantité sert à tester la dépendance aux ontologies.
    """
    return np.asarray(1.0 / np.maximum((shares**2).sum(axis=-1), 1e-12))


def summary(fit: CompositionFit, level: float) -> dict[str, Any]:
    info = fit.information_ratio if not np.isnan(fit.prior_var).any() else None
    return {
        "ontology_id": fit.ontology_id,
        "categories": fit.categories,
        "observations_used": fit.used,
        "excluded": fit.excluded,
        "median_information_ratio": None if info is None else float(np.median(info)),
        "cells_with_responses": int((fit.respondents > 0).sum()),
        "level": level,
    }
