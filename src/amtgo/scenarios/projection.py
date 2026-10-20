"""Projection de population sous un scénario S1 ou S2A (prompt §35-36).

La projection n'applique que des multiplicateurs **uniformes** sur la région
(croissance naturelle, solde migratoire exogène) : elle ne déplace personne entre
cellules. La relocalisation induite est mesurée (variation totale entre les
répartitions avant / après) et vérifiée nulle. En S2A, la réponse volontaire à
une réforme est un effet causal : elle n'est jamais simulée ici (M7).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from amtgo.errors import NormativeViolation
from amtgo.scenarios.model import MobilityRegime, Scenario, ScenarioDraws, assert_no_induced_displacement

# Tolérance numérique de la vérification de relocalisation (variation totale, sans unité).
RELOCATION_TOL = 1e-9


@dataclass(frozen=True)
class ProjectedPopulation:
    samples: np.ndarray  # (S, N)
    forced_migration: float  # toujours 0
    reform_induced_relocation: float  # part de la population déplacée entre cellules : 0
    voluntary_response: str  # "none" (S1) | "CAUSAL_EFFECT_UNKNOWN" (S2A sans réponse causale)


def relocation_share(before: np.ndarray, after: np.ndarray) -> float:
    """Variation totale maximale entre répartitions spatiales normalisées, sur les tirages."""
    a = before / before.sum(axis=1, keepdims=True)
    b = after / after.sum(axis=1, keepdims=True)
    return float(0.5 * np.abs(a - b).sum(axis=1).max())


def project_population(base: np.ndarray, scenario: Scenario, draws: ScenarioDraws) -> ProjectedPopulation:
    if scenario.mobility_regime is MobilityRegime.S2C:
        raise NormativeViolation(f"{scenario.scenario_id} : S2C est un diagnostic agrégé, aucune projection "
                                 "de population ni plan de déplacement n'est calculé (prompt §37)")
    if base.ndim != 2 or len(draws.population) != base.shape[0]:
        raise ValueError("population (S, N) et tirages de scénario incompatibles")
    out = base * draws.population[:, None]
    induced = relocation_share(base, out)
    if induced > RELOCATION_TOL:
        raise NormativeViolation(f"{scenario.scenario_id} : relocalisation induite {induced:.3g}")
    induced = 0.0
    assert_no_induced_displacement(scenario, forced=0.0, induced=induced)
    response = "none" if scenario.mobility_regime is MobilityRegime.S1 else "CAUSAL_EFFECT_UNKNOWN"
    return ProjectedPopulation(out, 0.0, induced, response)
