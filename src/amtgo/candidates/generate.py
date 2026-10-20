"""Algorithmes de génération : déterministes, multi-départ, contigus (prompt §38, §85).

Entrées : centres des cellules (LAEA, km), population moyenne par cellule,
graphe d'adjacence du maillage, noyau de liens. Aucune part de groupe.
"""

from __future__ import annotations

from collections import deque

import networkx as nx
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh


def canonical_labels(assign: np.ndarray) -> np.ndarray:
    """Étiquettes renumérotées par première apparition : deux partitions égales ont le même codage."""
    _, first = np.unique(assign, return_index=True)
    order = {int(assign[i]): k for k, i in enumerate(sorted(first))}
    return np.array([order[int(a)] for a in assign])


def weighted_kmeans(x: np.ndarray, w: np.ndarray, k: int, restarts: int, seed: int,
                    init: np.ndarray | None = None, iterations: int = 100) -> np.ndarray:
    """k-means pondéré (Lloyd), k-means++ ou centres imposés ; meilleure inertie sur ``restarts`` départs."""
    if k == 1:
        return np.zeros(len(x), dtype=int)
    rng = np.random.default_rng([seed, 11, k])
    best, best_inertia = None, np.inf
    for _ in range(1 if init is not None else restarts):
        if init is not None:
            centres = init.copy()
        else:
            centres = np.empty((k, x.shape[1]))
            centres[0] = x[rng.choice(len(x), p=w / w.sum())]
            for j in range(1, k):
                d2 = ((x[:, None, :] - centres[None, :j, :]) ** 2).sum(axis=2).min(axis=1)
                p = w * d2
                centres[j] = x[rng.choice(len(x), p=p / p.sum())] if p.sum() > 0 else x[rng.integers(len(x))]
        for _ in range(iterations):
            d2 = ((x[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
            assign = d2.argmin(axis=1)
            new = np.array([np.average(x[assign == j], axis=0, weights=w[assign == j])
                            if w[assign == j].sum() > 0 else centres[j] for j in range(k)])
            if np.allclose(new, centres):
                break
            centres = new
        inertia = float((w * d2[np.arange(len(x)), assign]).sum())
        if inertia < best_inertia - 1e-9 or best is None:
            best, best_inertia = assign, inertia
    assert best is not None
    return np.asarray(best)


def spectral_partition(kernel: sparse.csr_matrix, n: np.ndarray, k: int, restarts: int, seed: int) -> np.ndarray:
    """Coupe normalisée (Ng–Jordan–Weiss) du graphe des liens pondéré par la population."""
    if k == 1:
        return np.zeros(len(n), dtype=int)
    w = sparse.diags(n) @ kernel @ sparse.diags(n)
    w = w - sparse.diags(w.diagonal())
    deg = np.asarray(w.sum(axis=1)).ravel()
    inv = sparse.diags(1.0 / np.sqrt(np.maximum(deg, 1e-300)))
    m = (inv @ w @ inv).tocsr()
    if m.shape[0] <= 400:
        vals, vecs = np.linalg.eigh(m.toarray())
        vecs = vecs[:, np.argsort(vals)[::-1][:k]]
    else:
        v0 = np.random.default_rng([seed, 12]).uniform(size=m.shape[0])
        vals, vecs = eigsh(m, k=k, which="LA", v0=v0)
        vecs = vecs[:, np.argsort(vals)[::-1]]
    emb = vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12)
    return weighted_kmeans(emb, np.ones(len(n)), k, restarts, seed)


def community_partition(adjacency: list[list[int]], kernel: sparse.csr_matrix, n: np.ndarray,
                        resolution: float, seed: int) -> np.ndarray:
    """Louvain sur le graphe d'adjacence, arêtes pondérées par liens × populations."""
    g = nx.Graph()
    g.add_nodes_from(range(len(n)))
    k = kernel.tocsr()
    scale = 0.0
    edges = []
    for i, nbrs in enumerate(adjacency):
        for j in nbrs:
            if j > i:
                wt = float(k[i, j]) * n[i] * n[j]
                edges.append((i, j, wt))
                scale = max(scale, wt)
    g.add_weighted_edges_from((i, j, wt / scale if scale > 0 else 1.0) for i, j, wt in edges)
    comms = nx.community.louvain_communities(g, weight="weight", resolution=resolution, seed=seed)
    assign = np.zeros(len(n), dtype=int)
    for label, members in enumerate(sorted(comms, key=min)):
        assign[list(members)] = label
    return assign


def repair_contiguity(assign: np.ndarray, adjacency: list[list[int]], n: np.ndarray) -> tuple[np.ndarray, int]:
    """Chaque État devient connexe : ses composantes mineures (en population) rejoignent le voisin
    avec lequel elles partagent le plus d'arêtes. Déterministe ; renvoie le nombre de cellules déplacées."""
    a = assign.copy()
    moved = 0
    for _ in range(len(a)):
        changed = False
        for label in np.unique(a):
            comps = _components(np.flatnonzero(a == label), adjacency, a)
            if len(comps) <= 1:
                continue
            comps.sort(key=lambda c: (-n[c].sum(), min(c)))
            for comp in comps[1:]:
                counts: dict[int, int] = {}
                for i in comp:
                    for j in adjacency[i]:
                        if a[j] != label:
                            counts[int(a[j])] = counts.get(int(a[j]), 0) + 1
                if not counts:
                    continue  # composante isolée du maillage (île) : elle reste, c'est un fait géographique
                target = max(sorted(counts), key=lambda t: counts[t])
                a[comp] = target
                moved += len(comp)
                changed = True
        if not changed:
            break
    return canonical_labels(a), moved


def _components(members: np.ndarray, adjacency: list[list[int]], a: np.ndarray) -> list[list[int]]:
    left = set(int(i) for i in members)
    label = a[members[0]] if len(members) else -1
    out = []
    while left:
        start = min(left)
        comp, queue = [start], deque([start])
        left.discard(start)
        while queue:
            i = queue.popleft()
            for j in adjacency[i]:
                if j in left and a[j] == label:
                    left.discard(j)
                    comp.append(j)
                    queue.append(j)
        out.append(sorted(comp))
    return out


def is_contiguous(assign: np.ndarray, adjacency: list[list[int]]) -> bool:
    """Vrai si chaque État est connexe, à l'exception des composantes isolées du maillage lui-même."""
    mesh_components = _components(np.arange(len(assign)), adjacency, np.zeros(len(assign), dtype=int))
    for comp in mesh_components:
        sub = assign[comp]
        for label in np.unique(sub):
            members = np.array(comp)[sub == label]
            if len(_components(members, adjacency, assign)) > 1:
                return False
    return True
