"""Modèles d'observation (prompt §67, 03 §27) : chaque source garde sa vraisemblance.

Une observation o est reliée au vecteur latent Z (population par cellule) par
une fonctionnelle linéaire et un bruit gaussien (ADR-0013) :

    y_o = h_oᵀ Z + ε_o,   ε_o ~ N(0, r_o)

Hypothèse explicite (WE ASSUME) : **densité homogène à l'intérieur d'une
cellule**. C'est ce qui rend le compte d'une petite zone ou le total d'un
polygone linéaire en Z. Elle est rapportée dans chaque rapport.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.strtree import STRtree

from amtgo.core.enums import SupportType
from amtgo.data.observations import Observation
from amtgo.errors import InsufficientEvidence
from amtgo.geo.crs import to_equal_area
from amtgo.geo.mesh import Mesh
from amtgo.geo.support import KERNEL_POINTS, _disk_offsets, first_hits
from amtgo.measurement.manifest import LikelihoodModel, LikelihoodSpec


@dataclass(frozen=True)
class DesignRow:
    observation_id: str
    source_id: str
    cells: np.ndarray  # indices de cellules
    weights: np.ndarray  # h_o restreint à ces cellules
    y: float
    r: float  # variance du bruit d'observation
    outside_fraction: float  # part de la fonctionnelle hors du domaine maillé


class MeshIndex:
    """Index spatial du maillage en projection équivalente, partagé par les modèles."""

    def __init__(self, mesh: Mesh) -> None:
        self.mesh = mesh
        self.ids = list(mesh.cells)
        self.pos = {cid: k for k, cid in enumerate(self.ids)}
        self.geoms = [to_equal_area(mesh.cells[c].geometry) for c in self.ids]
        self.area = np.array([mesh.cells[c].area_km2 for c in self.ids])
        self.tree = STRtree(self.geoms)

    def __len__(self) -> int:
        return len(self.ids)


def _ea_count_density(obs: Observation, spec: LikelihoodSpec, idx: MeshIndex) -> DesignRow:
    """Compte d'une EA de surface a : y = a · densité moyenne sous le noyau de déplacement."""
    if obs.support_type not in (SupportType.POINT, SupportType.UNCERTAIN_POINT):
        raise InsufficientEvidence(f"{obs.id} : ea_count_density exige un support ponctuel")
    a = obs.attributes.get("ea_area_km2")
    if obs.value is None or obs.value.mean is None or not a:
        raise InsufficientEvidence(f"{obs.id} : compte ou surface d'EA manquants")
    geom = obs.geometry()
    assert geom is not None
    p = to_equal_area(geom)
    if obs.support_type is SupportType.UNCERTAIN_POINT:
        assert obs.displacement_km is not None
        pts = _disk_offsets(obs.displacement_km * 1000.0, KERNEL_POINTS) + np.array([p.x, p.y])
    else:
        pts = np.array([[p.x, p.y]])
    share = 1.0 / len(pts)
    cell_of = first_hits(idx.tree, pts)
    inside = cell_of >= 0
    outside = float((~inside).sum()) * share
    uniq, counts = np.unique(cell_of[inside], return_counts=True)
    acc = {int(k): float(c) * share for k, c in zip(uniq, counts, strict=True)}
    cells = np.array(sorted(acc), dtype=int)
    # densité de la cellule j = Z_j / A_j ; compte = a · Σ_j w_j Z_j / A_j
    weights = np.array([float(a) * acc[k] / idx.area[k] for k in cells])
    y = float(obs.value.mean)
    # Bruit de Poisson du comptage (≥ 1 pour éviter r = 0) plus erreur de représentativité.
    r = (max(y, 1.0) + (spec.representativeness_cv * y) ** 2) * spec.variance_inflation
    return DesignRow(str(obs.id), obs.source_id, cells, weights, y, r, outside)


def _area_total(obs: Observation, spec: LikelihoodSpec, idx: MeshIndex) -> DesignRow:
    """Total d'un polygone : y = Σ_j (|c_j ∩ P| / A_j) Z_j."""
    if obs.support_type not in (SupportType.ADMIN, SupportType.POLYGON):
        raise InsufficientEvidence(f"{obs.id} : area_total exige un support surfacique")
    if obs.value is None or obs.value.mean is None or obs.value.std is None:
        raise InsufficientEvidence(f"{obs.id} : total ou écart-type manquant")
    geom = obs.geometry()
    assert geom is not None
    poly = to_equal_area(geom)
    cells, weights = [], []
    covered = 0.0
    for k in sorted(int(i) for i in idx.tree.query(poly, predicate="intersects")):
        inter_km2 = idx.geoms[k].intersection(poly).area / 1e6
        if inter_km2 <= 0:
            continue
        cells.append(k)
        weights.append(inter_km2 / idx.area[k])
        covered += inter_km2
    total_km2 = poly.area / 1e6
    outside = max(0.0, 1.0 - covered / total_km2) if total_km2 else 1.0
    r = float(obs.value.std) ** 2 * spec.variance_inflation
    return DesignRow(str(obs.id), obs.source_id, np.array(cells, dtype=int), np.array(weights),
                     float(obs.value.mean), max(r, 1.0), outside)


_MODELS = {
    LikelihoodModel.EA_COUNT_DENSITY: _ea_count_density,
    LikelihoodModel.AREA_TOTAL: _area_total,
}


def design_row(obs: Observation, spec: LikelihoodSpec, idx: MeshIndex) -> DesignRow:
    return _MODELS[spec.model](obs, spec, idx)
