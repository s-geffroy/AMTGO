"""Benchmark exact sur petite zone (prompt §47, 05 §9, Gate O).

Sur une grille 4×4 fictive, toutes les bipartitions contiguës sont énumérées.
Chaque heuristique du générateur est comparée à l'optimum exact **de son propre
critère** — inertie pondérée pour le k-means, coupe normalisée pour la coupe
spectrale — en multi-départ : écart relatif (J_heuristique − J_exact) / J_exact.

Le front exact de (J_G, J_F) — liens coupés, liens du groupe minoritaire coupés —
est aussi calculé : il est fait de micro-territoires (une cellule détachée). C'est
le Goodhart « micro-territoires » (05 §14) : la coupe seule ne doit jamais être
un objectif isolé ; les coûts fixes réels (J_inst, J_V) le contrebalancent.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np
from scipy import sparse

from amtgo.candidates.generate import repair_contiguity, spectral_partition, weighted_kmeans

NX, NY = 4, 4


def _adjacency() -> list[list[int]]:
    return [[(y2 * NX + x2) for x2, y2 in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
             if 0 <= x2 < NX and 0 <= y2 < NY] for y in range(NY) for x in range(NX)]


def _connected(cells: list[int], adj: list[list[int]]) -> bool:
    if not cells:
        return False
    member = set(cells)
    seen, queue = {cells[0]}, deque([cells[0]])
    while queue:
        i = queue.popleft()
        for j in adj[i]:
            if j in member and j not in seen:
                seen.add(j)
                queue.append(j)
    return len(seen) == len(member)


def contiguous_bipartitions() -> np.ndarray:
    """(P, 16) : toutes les bipartitions dont les deux parts sont connexes (cellule 0 dans la part 0)."""
    adj = _adjacency()
    n = NX * NY
    out = []
    for mask in range(1 << (n - 1)):
        a = np.array([0] + [(mask >> (i - 1)) & 1 for i in range(1, n)])
        p0, p1 = [int(i) for i in np.flatnonzero(a == 0)], [int(i) for i in np.flatnonzero(a == 1)]
        if p1 and _connected(p0, adj) and _connected(p1, adj):
            out.append(a)
    return np.array(out)


def world() -> tuple[np.ndarray, np.ndarray, np.ndarray, sparse.csr_matrix]:
    """Centres (km), population, effectif du groupe minoritaire, noyau de liens (fictifs)."""
    xy = np.array([(x, y) for y in range(NY) for x in range(NX)], dtype=float) * 10.0
    d = np.linalg.norm(xy[:, None, :] - xy[None, :, :], axis=2)
    kernel = sparse.csr_matrix(np.where(d <= 30.0, np.exp(-d / 12.0), 0.0))
    pop = 100.0 + 400.0 * np.exp(-np.linalg.norm(xy - [5.0, 5.0], axis=1) / 15.0)  # une ville au sud-ouest
    minority = np.where(xy[:, 0] >= 20.0, 0.5, 0.1) * pop  # minorité concentrée à l'est
    return xy, pop, minority, kernel


def objectives(parts: np.ndarray, kernel: sparse.csr_matrix, pop: np.ndarray, minority: np.ndarray) -> np.ndarray:
    """(P, 2) : J_G = part des liens de population coupés ; J_F = part des liens du groupe coupés."""
    coo = sparse.triu(kernel, k=1).tocoo()
    cut = parts[:, coo.row] != parts[:, coo.col]  # (P, E)
    out = []
    for n in (pop, minority):
        w = coo.data * n[coo.row] * n[coo.col]
        out.append((cut * w).sum(axis=1) / w.sum())
    return np.column_stack(out)


def pareto_mask(points: np.ndarray) -> np.ndarray:
    keep = np.ones(len(points), dtype=bool)
    for i, p in enumerate(points):
        if keep[i]:
            dominated = np.all(points <= p, axis=1) & np.any(points < p, axis=1)
            if dominated.any():
                keep[i] = False
    return keep


def inertia(parts: np.ndarray, xy: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Inertie pondérée (critère du k-means) de chaque bipartition, (P,)."""
    out = np.zeros(len(parts))
    for k in (0, 1):
        m = parts == k
        wk = m * w
        tot = wk.sum(axis=1, keepdims=True)
        c = (wk @ xy) / np.maximum(tot, 1e-12)  # (P, 2)
        d2 = ((xy[None, :, :] - c[:, None, :]) ** 2).sum(axis=2)
        out += (wk * d2).sum(axis=1)
    return out


def normalized_cut(parts: np.ndarray, kernel: sparse.csr_matrix, w: np.ndarray) -> np.ndarray:
    """Coupe normalisée (critère de la coupe spectrale) sur le graphe pondéré par la population."""
    a = (sparse.diags(w) @ kernel @ sparse.diags(w)).toarray()
    np.fill_diagonal(a, 0.0)
    deg = a.sum(axis=1)
    out = np.zeros(len(parts))
    for k in (0, 1):
        m = (parts == k).astype(float)
        cut = np.einsum("pi,ij,pj->p", m, a, 1.0 - m)
        out += cut / np.maximum(m @ deg, 1e-12)
    return out


def run(seeds: tuple[int, ...] = (0, 1, 2, 3, 4), restarts: int = 4) -> dict[str, Any]:
    xy, pop, minority, kernel = world()
    parts = contiguous_bipartitions()
    adj = _adjacency()
    out: dict[str, Any] = {"partitions_enumerated": len(parts), "seeds": list(seeds)}

    def km(s: int) -> np.ndarray:
        return weighted_kmeans(xy, pop, 2, restarts, s)

    def sp(s: int) -> np.ndarray:
        return spectral_partition(kernel, pop, 2, restarts, s)

    criteria: dict[str, tuple[Callable[[int], np.ndarray], Callable[[np.ndarray], np.ndarray]]] = {
        "kmeans": (km, lambda p: inertia(p, xy, pop)),
        "spectral": (sp, lambda p: normalized_cut(p, kernel, pop))}
    for name, (heuristic, criterion) in criteria.items():
        exact = float(criterion(parts).min())
        sols = []
        for s in seeds:
            a, _ = repair_contiguity(heuristic(s), adj, pop)  # comme dans le pipeline (M8)
            sols.append(a if a[0] == 0 else 1 - a)
        values = criterion(np.array(sols))
        gaps = (values - exact) / max(abs(exact), 1e-12)
        out[name] = {"exact_optimum": exact, "heuristic_values": values.round(6).tolist(),
                     "relative_gaps": gaps.round(6).tolist(), "best_gap": float(gaps.min()),
                     "distinct_solutions": len({tuple(a) for a in sols})}
    obj = objectives(parts, kernel, pop, minority)
    front_idx = np.flatnonzero(pareto_mask(obj))
    out["cut_only_front"] = {"size": len(front_idx), "points": obj[front_idx].round(4).tolist(),
                             "smallest_state_cells": [int(min((parts[i] == 0).sum(), (parts[i] == 1).sum()))
                                                      for i in front_idx]}
    return out
