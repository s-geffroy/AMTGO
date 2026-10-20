"""Exécution en ensemble sous plusieurs ontologies (prompt §17, 05 §6).

Aucun résultat ne doit dépendre d'une classification unique sans être marqué.
À M4, la quantité comparée est **descriptive** : le motif spatial de la
diversité (nombre effectif de catégories) à l'échelle de la grille de
référence. S^ontology se définit comme la corrélation de rang de ce motif
entre ontologies, tronquée à [0,1] (ADR-0016) ; à partir de M5, il portera sur
les sorties D/F/I.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np

from amtgo.measurement.composition import aggregate_shares, effective_number


def _rank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    ranks[order] = np.arange(len(x))
    # Ex aequo : rang moyen.
    for v in np.unique(x):
        m = x == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    return ranks


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or np.all(a == a[0]) or np.all(b == b[0]):
        return float("nan")
    return float(np.corrcoef(_rank(a), _rank(b))[0, 1])


def ontology_stability(eng_by_ontology: dict[str, np.ndarray]) -> dict[str, Any]:
    """``eng_by_ontology`` : nombre effectif médian par cellule de référence, par ontologie."""
    pairs: list[dict[str, Any]] = []
    for a, b in combinations(sorted(eng_by_ontology), 2):
        ea, eb = eng_by_ontology[a], eng_by_ontology[b]
        rho = spearman(ea, eb)
        pairs.append({"a": a, "b": b, "spearman": rho,
                      "mean_abs_log_ratio": float(np.mean(np.abs(np.log(ea / eb))))})
    finite = [float(p["spearman"]) for p in pairs if np.isfinite(p["spearman"])]
    s_ont = float(np.clip(min(finite), 0.0, 1.0)) if finite else float("nan")
    return {"pairs": pairs, "s_ontology": s_ont}


def reference_summary(shares: np.ndarray, population: np.ndarray, weights: np.ndarray,
                      categories: list[str], level: float) -> dict[str, Any]:
    """Résumé agrégé (domaine entier + motif à l'échelle de référence) ; aucune donnée par cellule."""
    a = (1 - level) / 2
    domain = aggregate_shares(shares, population, weights.sum(axis=0, keepdims=True).clip(max=1.0))[:, 0, :]
    ref = aggregate_shares(shares, population, weights)  # (S, D, K)
    eng = effective_number(ref)  # (S, D)
    return {
        "domain_shares": {c: {"mean": float(domain[:, i].mean()),
                              "interval": [float(np.quantile(domain[:, i], a)),
                                           float(np.quantile(domain[:, i], 1 - a))]}
                          for i, c in enumerate(categories)},
        "effective_number_median_by_reference_cell": np.median(eng, axis=0).tolist(),
    }
