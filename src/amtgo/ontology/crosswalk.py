"""Application probabiliste d'un crosswalk : π_b = Σ_a P(b | a) π_a, avec incertitude.

Chaque ligne P(· | a) est tirée d'une loi de Dirichlet centrée sur la ligne
déclarée, de concentration ``concentration`` : un crosswalk mal documenté
propage une large incertitude au lieu d'une fausse précision. La masse
``UNMAPPED`` est conservée et rapportée : elle n'est jamais redistribuée.
"""

from __future__ import annotations

import numpy as np

from amtgo.ontology.model import UNMAPPED, Ontology, OntologyCrosswalk


def target_space(target: Ontology) -> list[str]:
    return [*target.leaf_ids, UNMAPPED]


def sample_matrices(cw: OntologyCrosswalk, source: Ontology, target: Ontology, n_samples: int,
                    seed: int) -> np.ndarray:
    """(S, A, B+1) : tirages de la matrice P(b | a), colonnes = feuilles cibles + UNMAPPED."""
    cw.check_against(source, target)
    rng = np.random.default_rng([seed, 17])
    cols = target_space(target)
    rows = {r.source_concept: r for r in cw.rows}
    out = np.zeros((n_samples, len(source.leaf_ids), len(cols)))
    for i, a in enumerate(source.leaf_ids):
        row = rows[a]
        p = np.array([row.targets.get(b, 0.0) for b in cols])
        support = p > 0
        alpha = p[support] * row.concentration
        out[:, i, support] = rng.dirichlet(alpha, size=n_samples)
    return out


def apply(shares: np.ndarray, matrices: np.ndarray) -> np.ndarray:
    """``shares`` (S, N, A) → (S, N, B+1), tirage par tirage."""
    return np.asarray(np.einsum("sna,sab->snb", shares, matrices))


def compose(first: np.ndarray, second: np.ndarray, unmapped_index_mid: int) -> np.ndarray:
    """Composition A→B→C : la masse UNMAPPED de B reste UNMAPPED en C (jamais réattribuée)."""
    s, a, _ = first.shape
    c = second.shape[2]
    out = np.zeros((s, a, c))
    keep = [k for k in range(first.shape[2]) if k != unmapped_index_mid]
    out += np.einsum("sab,sbc->sac", first[:, :, keep], second)
    out[:, :, -1] += first[:, :, unmapped_index_mid]
    return out
