"""Affectation d'observations ponctuelles à un maillage, sans point-in-polygon naïf.

Un point géomasqué (UNCERTAIN_POINT, 03 §6) est une distribution : on répartit
sa masse sur des positions déterministes réparties uniformément dans le disque
de déplacement. Un POINT exact est affecté à la cellule qui le contient. C'est
une approximation du noyau de déplacement, pas encore un modèle de mesure (M3).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.strtree import STRtree

from amtgo.core.enums import SupportType
from amtgo.data.observations import Observation
from amtgo.errors import InsufficientEvidence
from amtgo.geo.crs import to_equal_area
from amtgo.geo.mesh import Mesh

# Nombre de positions du noyau de déplacement : résolution numérique, pas paramètre
# scientifique (l'erreur d'intégration est en O(1/n)).
KERNEL_POINTS = 64
_GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


def _disk_offsets(radius_m: float, n: int) -> np.ndarray:
    """Spirale de Fibonacci (Vogel) : n points d'aire égale dans un disque, déterministe."""
    k = np.arange(n) + 0.5
    r = radius_m * np.sqrt(k / n)
    theta = k * _GOLDEN
    return np.column_stack([r * np.cos(theta), r * np.sin(theta)])


def first_hits(tree: STRtree, pts: np.ndarray) -> np.ndarray:
    """Pour chaque point (n, 2), indice de la géométrie qui le contient, −1 sinon.

    Requête vectorisée ; un point sur une arête partagée va à la plus petite géométrie
    d'indice (règle déterministe, identique à la version scalaire).
    """
    out = np.full(len(pts), -1, dtype=int)
    if len(pts) == 0:
        return out
    pi, gi = tree.query(shapely.points(pts), predicate="intersects")
    order = np.lexsort((gi, pi))
    pi, gi = pi[order], gi[order]
    first = np.ones(len(pi), dtype=bool)
    first[1:] = pi[1:] != pi[:-1]
    out[pi[first]] = gi[first]
    return out


@dataclass(frozen=True)
class Allocation:
    values: dict[str, float]
    total_in: float
    unallocated: float


def allocate_point_masses(observations: Iterable[Observation], mesh: Mesh) -> Allocation:
    """Répartit la moyenne de ``value`` de chaque observation ponctuelle sur ``mesh``."""
    ids = list(mesh.cells)
    geoms = [to_equal_area(mesh.cells[c].geometry) for c in ids]
    tree = STRtree(geoms)
    out: dict[str, float] = defaultdict(float)
    total = 0.0
    lost = 0.0
    for obs in observations:
        if obs.support_type not in (SupportType.POINT, SupportType.UNCERTAIN_POINT):
            raise InsufficientEvidence(f"{obs.id} : support {obs.support_type.value} non ponctuel")
        if obs.value is None or obs.value.mean is None:
            raise InsufficientEvidence(f"{obs.id} : pas de valeur centrale")
        geom = obs.geometry()
        assert geom is not None
        p = to_equal_area(geom)
        mass = obs.value.mean
        total += mass
        if obs.support_type is SupportType.POINT:
            pts = np.array([[p.x, p.y]])
        else:
            assert obs.displacement_km is not None
            pts = _disk_offsets(obs.displacement_km * 1000.0, KERNEL_POINTS) + np.array([p.x, p.y])
        share = mass / len(pts)
        cell_of = first_hits(tree, pts)
        lost += float((cell_of < 0).sum()) * share
        for k in cell_of[cell_of >= 0]:
            out[ids[int(k)]] += share
    return Allocation(dict(sorted(out.items())), total, lost)
