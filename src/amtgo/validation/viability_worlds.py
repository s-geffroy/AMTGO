"""Monde synthétique V : viabilité contextuelle à vérité connue (M6, ADR-0010).

Quatre territoires FICTIFS aux comptes déclarés (par habitant) :

- ``large_dense`` : grand, base fiscale forte, services peu coûteux ;
- ``large_sparse`` : grand, base faible, services coûteux (faible densité) ;
- ``small_dense`` : petit, comptes de ``large_dense`` ;
- ``small_balanced`` : petit, recettes à peine supérieures au coût des services.

Propriétés attendues (qualitatives) : la viabilité d'un même territoire change
avec le régime (01 §8, spec 14 §6) ; aucun seuil de taille ne la détermine ;
au régime d'observation, les coefficients exploratoires n'ont aucun effet.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from amtgo.institutions.regimes import ConstitutionalRegime
from amtgo.institutions.viability import (
    FiscalUnion,
    Territory,
    ViabilityAssessment,
    ViabilityContext,
    compute_viability,
    draw_model,
)
from amtgo.manifests.normative import ViabilityThresholds
from amtgo.manifests.viability import ExploratoryEffects, SovereignOverhead, ViabilityManifest
from amtgo.scenarios.model import (
    ClimateAxis,
    EconomyAxis,
    InfrastructureAxis,
    Interval,
    MigrationAxis,
    MobilityRegime,
    PopulationAxis,
    Scenario,
    SecurityAxis,
    UrbanizationAxis,
    draw_scenario,
)

# territoire : (population, recettes par habitant, coût des services par habitant)
TERRITORIES: dict[str, tuple[float, float, float]] = {
    "large_dense": (1.0e6, 300.0, 160.0),
    "large_sparse": (1.0e6, 140.0, 260.0),
    "small_dense": (2.0e5, 300.0, 160.0),
    "small_balanced": (2.0e5, 190.0, 170.0),
}
DRAWS = 400
NOISE = 0.01  # erreur relative des comptes

_POINT = Interval(lo=0.0, hi=0.0)
_ONE = Interval(lo=1.0, hi=1.0)


def neutral_scenario() -> Scenario:
    """S1 sans évolution : isole l'effet du régime."""
    return Scenario(
        scenario_id="world_v_neutral", version="1", description="monde V : aucun changement exogène",
        mobility_regime=MobilityRegime.S1, horizon_years=1,
        population=PopulationAxis(annual_growth=_POINT), climate=ClimateAxis(modelled=False),
        urbanization=UrbanizationAxis(service_cost_multiplier=_ONE),
        economy=EconomyAxis(annual_fiscal_base_growth=_POINT),
        migration=MigrationAxis(exogenous_annual_net_rate=_POINT),
        infrastructure=InfrastructureAxis(market_access_multiplier=_ONE),
        security=SecurityAxis(security_cost_multiplier=_ONE))


def world_model(observed: str) -> ViabilityManifest:
    return ViabilityManifest(
        model_id="world_v", version="1", description="monde V", fiscal_source="world_v",
        revenue_variable="revenue", cost_variable="cost", observed_regime=observed,
        regime_sensitivity=(observed,), level="state",
        sovereign_overhead=SovereignOverhead(administration=Interval(lo=2.0e6, hi=3.0e6),
                                             security=Interval(lo=4.0e6, hi=6.0e6)),
        exploratory=ExploratoryEffects(market_access_elasticity=Interval(lo=0.0, hi=0.3),
                                       infrastructure_cost_reduction=Interval(lo=0.0, hi=0.2),
                                       source="monde V (fictif)"),
        union_closure="monde V : les quatre territoires forment l'union")


def world_union(seed: int = 0) -> FiscalUnion:
    rng = np.random.default_rng([seed, 8])
    ids = list(TERRITORIES)
    pop = np.array([TERRITORIES[t][0] for t in ids])
    rev = np.array([TERRITORIES[t][0] * TERRITORIES[t][1] for t in ids])
    cost = np.array([TERRITORIES[t][0] * TERRITORIES[t][2] for t in ids])

    def noisy(x: np.ndarray) -> np.ndarray:
        return x * (1.0 + NOISE * rng.standard_normal((DRAWS, len(ids))))

    return FiscalUnion(ids, np.tile(pop, (DRAWS, 1)), noisy(rev), noisy(cost))


def evaluate(regimes: dict[str, ConstitutionalRegime], observed: str, thresholds: ViabilityThresholds,
             seed: int = 0) -> dict[str, dict[str, ViabilityAssessment]]:
    """{régime: {territoire: évaluation}} sous le scénario neutre."""
    sc = neutral_scenario()
    model = world_model(observed)
    exploratory, overhead = draw_model(model, DRAWS, seed)
    ctx = ViabilityContext(world_union(seed), model, regimes[observed], thresholds,
                           draw_scenario(sc, DRAWS, seed), exploratory, overhead)
    return {rid: {t: compute_viability(Territory(t, "state"), r, sc, ctx) for t in TERRITORIES}
            for rid, r in regimes.items()}


def checks(res: dict[str, dict[str, ViabilityAssessment]], observed: str) -> list[tuple[str, bool, str]]:
    r0, r3 = res["R0_CURRENT_LIKE"], res["R3_FEDERAL_CONTINENTAL"]
    sb0, sb3 = r0["small_balanced"], r3["small_balanced"]

    def cov(a: ViabilityAssessment) -> str:
        return "—" if a.coverage is None else f"{a.coverage.mean:.2f}"

    try:
        bool(sb0)
        no_truth = False
    except TypeError:
        no_truth = True
    return [
        ("V : un même petit territoire, non viable sous R0, est viable sous R3 (transferts, défense mutualisée)",
         sb0.status.value == "NOT_VIABLE" and sb3.status.value == "VIABLE",
         f"small_balanced : R0 {sb0.status.value} ({cov(sb0)}) ; R3 {sb3.status.value} ({cov(sb3)})"),
        ("V : aucun seuil de taille — un petit territoire viable, un grand non, sous le même régime",
         r0["small_dense"].status.value == "VIABLE" and r0["large_sparse"].status.value == "NOT_VIABLE",
         f"R0 : small_dense {r0['small_dense'].status.value} ; large_sparse {r0['large_sparse'].status.value}"),
        ("V : au régime d'observation, les coefficients exploratoires n'ont aucun effet",
         not any(a.exploratory_dependency for a in res[observed].values()),
         f"dépendances sous {observed} : {sum(a.exploratory_dependency for a in res[observed].values())}"),
        ("V : une viabilité n'a pas de valeur de vérité hors contexte (bool() lève)", no_truth,
         sb0.statement()),
    ]


def summary(res: dict[str, dict[str, ViabilityAssessment]]) -> dict[str, Any]:
    return {rid: {t: {"status": a.status.value, "coverage": None if a.coverage is None else a.coverage.mean,
                      "exploratory_dependency": a.exploratory_dependency} for t, a in by_t.items()}
            for rid, by_t in res.items()}
