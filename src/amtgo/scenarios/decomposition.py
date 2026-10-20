"""Décomposition d'un effet sous mobilité volontaire (S2A, prompt §36).

Pour un résultat J(G, n) — partition G, population n (tirages en première
dimension) — et une réforme G0 → G1 suivie d'une réponse volontaire n0 → n1 :

    direct       = J(G1, n0)    − J(G0, n0)      réforme à population fixe
    composition  = J(G1, n_mix) − J(G1, n0)      réponse dans les zones réformées
    spillover    = J(G1, n1)    − J(G1, n_mix)   réponse hors des zones réformées

où n_mix prend n1 dans les zones réformées et n0 ailleurs. La somme vaut
exactement l'effet total. Sans réponse volontaire identifiée (bibliothèque
causale, M7), composition et spillover sont CAUSAL_EFFECT_UNKNOWN : jamais nuls.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from amtgo.core.uncertainty import UncertainValue

Outcome = Callable[[Any, np.ndarray], np.ndarray]


@dataclass(frozen=True)
class EffectDecomposition:
    direct: UncertainValue
    composition: UncertainValue | None
    spillover: UncertainValue | None
    total: UncertainValue | None
    status: str  # "DECOMPOSED" | "CAUSAL_EFFECT_UNKNOWN"
    response_source: str | None


def decompose_voluntary_effect(outcome: Outcome, before: Any, after: Any, n0: np.ndarray,
                               n1: np.ndarray | None, reformed: np.ndarray,
                               response_source: str | None = None) -> EffectDecomposition:
    j00 = outcome(before, n0)
    j10 = outcome(after, n0)
    direct = UncertainValue.from_samples(j10 - j00)
    if n1 is None:
        return EffectDecomposition(direct, None, None, None, "CAUSAL_EFFECT_UNKNOWN", None)
    if not response_source:
        raise ValueError("S2A : une réponse de mobilité doit citer sa source causale (volontaire)")
    if n1.shape != n0.shape or reformed.shape != (n0.shape[1],):
        raise ValueError("formes incompatibles entre n0, n1 et le masque des zones réformées")
    if not np.allclose(n1.sum(axis=tuple(range(1, n1.ndim))), n0.sum(axis=tuple(range(1, n0.ndim))), rtol=1e-9):
        raise ValueError("S2A : la mobilité volontaire conserve la population de la région")
    mask = reformed.reshape((1, -1) + (1,) * (n0.ndim - 2))
    n_mix = np.where(mask, n1, n0)
    j1m = outcome(after, n_mix)
    j11 = outcome(after, n1)
    return EffectDecomposition(
        direct=direct, composition=UncertainValue.from_samples(j1m - j10),
        spillover=UncertainValue.from_samples(j11 - j1m), total=UncertainValue.from_samples(j11 - j00),
        status="DECOMPOSED", response_source=response_source)
