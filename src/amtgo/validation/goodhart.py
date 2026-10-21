"""Red-team Goodhart du solveur (05 §14, 01 §17).

Quand une métrique devient objectif, le solveur peut l'exploiter. On construit
des **attaques** sur la géométrie du statu quo et on les évalue comme des
candidats ; une attaque qui atteint le front sans être signalée est une faille
(« chaque loophole découvert devient test de régression »).

- ``micro_territory`` : la cellule la moins peuplée devient un État (réduire D) ;
- ``artificial_metropolis`` : la cellule la plus peuplée et ses voisines forment
  une cité-État (métropole artificielle) ;
- ``pathological_border`` : une cellule sur deux le long de la frontière change
  d'État (frontière en dents de scie) ;
- l'overlay vide et le transfert de coûts au niveau continental se testent sur
  les modules eux-mêmes (tests de régression), pas sur une géométrie.

Les détecteurs (part de population, part de surface, compacité de Polsby–Popper,
part de cellules frontalières en saillie) **signalent** pour revue humaine ; ils
n'excluent rien et ne pondèrent rien (il n'existe aucun seuil universel de
taille d'État, 01 §8).

Faille trouvée en M11 sur le pilote : la frontière en dents de scie atteignait
le front sans signalement — elle améliore J_V en déplaçant des cellules
fiscalement riches vers l'État le plus faible, et la compacité globale d'un État
(0,35) ne la distingue pas des communautés de Louvain (0,32–0,41). La part de
cellules en saillie (≥ 0,37 contre ≤ 0,07 pour tous les candidats générés) la
distingue : c'est le détecteur ``pathological_border``.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from shapely import unary_union
from shapely.geometry.base import BaseGeometry

ATTACK_PREFIX = "GOODHART_"


def border_protrusion_share(assign: np.ndarray, adjacency: list[list[int]]) -> float:
    """Part des cellules frontalières dont la majorité des voisines est dans un autre État."""
    border = [i for i, nb in enumerate(adjacency) if any(assign[j] != assign[i] for j in nb)]
    if not border:
        return 0.0
    spikes = [i for i in border if sum(assign[j] != assign[i] for j in adjacency[i]) > len(adjacency[i]) / 2]
    return len(spikes) / len(border)


def state_shapes(geoms_equal_area: list[BaseGeometry], assign: np.ndarray, pop: np.ndarray,
                 adjacency: list[list[int]]) -> dict[str, float]:
    """Plus petites parts de population et de surface d'un État, compacité minimale, saillies."""
    areas = np.array([g.area for g in geoms_equal_area])
    total_pop, total_area = float(pop.sum()), float(areas.sum())
    pop_shares, area_shares, compact = [], [], []
    for s in np.unique(assign):
        mask = assign == s
        shape = unary_union([geoms_equal_area[i] for i in np.where(mask)[0]])
        pop_shares.append(float(pop[mask].sum()) / max(total_pop, 1e-300))
        area_shares.append(float(areas[mask].sum()) / max(total_area, 1e-300))
        compact.append(4.0 * math.pi * shape.area / max(shape.length ** 2, 1e-300))
    return {"min_state_population_share": min(pop_shares), "min_state_area_share": min(area_shares),
            "min_compactness": min(compact), "border_protrusion_share": border_protrusion_share(assign, adjacency)}


def flags(shapes: dict[str, float], thresholds: Any) -> list[str]:
    """Signalements Goodhart d'une géométrie (``thresholds`` : ``GoodhartThresholds``)."""
    out = []
    if shapes["min_state_population_share"] < thresholds.micro_state_population_share:
        out.append("micro_state_population")
    if shapes["min_state_area_share"] < thresholds.micro_state_area_share:
        out.append("micro_state_area")
    if shapes["min_compactness"] < thresholds.min_compactness:
        out.append("pathological_shape")
    if shapes["border_protrusion_share"] > thresholds.max_border_protrusion_share:
        out.append("pathological_border")
    return out


def attacks(sq: np.ndarray, adjacency: list[list[int]], pop: np.ndarray) -> dict[str, np.ndarray]:
    """Géométries d'attaque construites sur le statu quo (niveau des États)."""
    n_states = int(sq.max()) + 1
    out: dict[str, np.ndarray] = {}
    micro = sq.copy()
    micro[int(np.argmin(np.where(pop > 0, pop, np.inf)))] = n_states
    out["micro_territory"] = micro
    metro = sq.copy()
    core = int(np.argmax(pop))
    metro[[core, *adjacency[core]]] = n_states
    out["artificial_metropolis"] = metro
    border = sorted(i for i, nb in enumerate(adjacency) if sq[i] == 0 and any(sq[j] != 0 for j in nb))
    if n_states >= 2 and border:
        saw = sq.copy()
        for i in border[::2]:
            saw[i] = next(sq[j] for j in adjacency[i] if sq[j] != 0)
        out["pathological_border"] = saw
    return {f"{ATTACK_PREFIX}{k}": _relabel(v) for k, v in out.items()}


def _relabel(a: np.ndarray) -> np.ndarray:
    _, inv = np.unique(a, return_inverse=True)
    return np.asarray(inv, dtype=np.int64)
