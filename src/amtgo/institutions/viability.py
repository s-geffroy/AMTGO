"""Viabilité conditionnelle V_k(r, s) (prompt §29, 02 §14, 01 §8, spec 14 §6).

    V_k(r) = f(service capacity, fiscal base, transfers(r), market access(r),
               infrastructure(r), security(r))

Toujours ``compute_viability(territory, regime, scenario, context)`` : il
n'existe aucun ``is_viable(territory)`` et une évaluation n'a pas de valeur de
vérité hors contexte (``bool()`` lève). Il n'y a aucun seuil de taille, de
surface ou d'autarcie : seule la couverture d'un panier de services est
comparée au seuil normatif τ_V.

Couverture du territoire k, par tirage :

    cov_k = (R_k + T_k − O_k) / C_k

- R_k : recettes propres observées × croissance (scénario) × (MA_k(r,s)/MA_k(r_obs))^γ,
  avec l'accès au marché MA_k = s_k + (1 − s_k)·min(1, intégration_r × infra_s),
  s_k la part de population de k dans l'union ;
- T_k : transferts budgétairement neutres de l'union — péréquation (part e_r de
  l'écart par habitant sous la moyenne) et mise en commun (part p_r redistribuée
  par habitant) ;
- O_k : surcoûts fixes de souveraineté — administration, plus sécurité non
  mutualisée (1 − d_r)·F_sec ; la part mutualisée d_r·F_sec n'est payée qu'une
  fois par l'union, au prorata de la population ;
- C_k : coût du panier de services observé × population × climat × urbanisation
  × (1 − δ·i_r)/(1 − δ·i_obs).

γ et δ viennent de la bibliothèque causale gelée (M7) : à défaut d'effet identifié,
des bornes I7, jamais des faits causaux ; un effet inconnu rend la viabilité UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from amtgo.causal.library import CausalAnswer
from amtgo.core.uncertainty import UncertainValue
from amtgo.institutions.regimes import ConstitutionalRegime
from amtgo.manifests.normative import ViabilityThresholds
from amtgo.manifests.viability import ViabilityManifest
from amtgo.scenarios.model import Scenario, ScenarioDraws


class ViabilityStatus(StrEnum):
    VIABLE = "VIABLE"
    NOT_VIABLE = "NOT_VIABLE"
    UNCERTAIN = "UNCERTAIN"
    UNKNOWN = "UNKNOWN"  # comptes fiscaux absents : jamais « viable » par défaut


@dataclass(frozen=True)
class Territory:
    territory_id: str
    level: str


@dataclass(frozen=True)
class FiscalUnion:
    """Comptes des territoires de l'union (tirages en première dimension, forme (S, K))."""

    territory_ids: list[str]
    population: np.ndarray
    revenue: np.ndarray  # recettes propres annuelles observées
    service_cost: np.ndarray  # coût annuel du panier de services observé

    def index(self, territory: Territory) -> int:
        try:
            return self.territory_ids.index(territory.territory_id)
        except ValueError as exc:
            raise KeyError(f"territoire {territory.territory_id} hors de l'union évaluée") from exc


@dataclass(frozen=True)
class ViabilityContext:
    union: FiscalUnion | None  # None : comptes fiscaux absents → UNKNOWN
    model: ViabilityManifest
    observed_regime: ConstitutionalRegime
    thresholds: ViabilityThresholds
    draws: ScenarioDraws  # tirages du scénario évalué
    effects: tuple[CausalAnswer, CausalAnswer]  # γ (accès au marché), δ (infrastructures) : bibliothèque gelée
    exploratory: np.ndarray  # (S, 2) : γ, δ par tirage
    overhead: np.ndarray  # (S, 2) : F_admin, F_sec par tirage


@dataclass(frozen=True)
class ViabilityAssessment:
    territory_id: str
    regime_id: str
    scenario_id: str
    status: ViabilityStatus
    coverage: UncertainValue | None
    p_shortfall: float | None
    transfer_share: UncertainValue | None  # T_k / C_k : dépendance aux transferts
    overhead_share: UncertainValue | None  # O_k / C_k : poids des coûts fixes de souveraineté
    exploratory_dependency: bool  # le statut change entre les bornes des coefficients I7

    def __bool__(self) -> bool:
        raise TypeError("une viabilité n'a pas de valeur de vérité hors contexte : lire status, "
                        "regime_id et scenario_id (prompt §29)")

    def statement(self) -> str:
        """Formulation 08 §16 : toujours sous un régime, un scénario, avec transferts."""
        if self.status is ViabilityStatus.UNKNOWN or self.coverage is None:
            return (f"{self.territory_id} : viabilité UNKNOWN sous {self.regime_id}, scénario "
                    f"{self.scenario_id} (comptes fiscaux absents)")
        assert self.transfer_share is not None
        dep = " ; dépend des bornes d'effets non identifiés" if self.exploratory_dependency else ""
        return (f"{self.territory_id} : {self.status.value} sous {self.regime_id}, scénario {self.scenario_id}, "
                f"couverture {self.coverage.mean:.2f} [{self.coverage.lower:.2f}, {self.coverage.upper:.2f}], "
                f"transferts {self.transfer_share.mean:+.2f} du coût des services{dep}")


def union_transfers(revenue: np.ndarray, population: np.ndarray, regime: ConstitutionalRegime) -> np.ndarray:
    """Transferts nets (S, K), budgétairement neutres : Σ_k T_k = 0 pour chaque tirage.

    Péréquation : part e_r de l'écart à la moyenne par habitant, financée au prorata des
    recettes ; mise en commun : part p_r des recettes redistribuée par habitant.
    """
    f = regime.fiscal_transfer_rules
    total_r = revenue.sum(axis=1, keepdims=True)
    total_p = population.sum(axis=1, keepdims=True)
    gap = np.clip(total_r / total_p - revenue / population, 0.0, None) * population
    equalization = f.equalization_rate * (gap - gap.sum(axis=1, keepdims=True) * revenue / total_r)
    pooled = f.pooled_revenue_share * (population / total_p * total_r - revenue)
    return np.asarray(equalization + pooled)


def _coverage(union: FiscalUnion, regime: ConstitutionalRegime, ctx: ViabilityContext,
              gamma: np.ndarray, delta: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Couverture, part des transferts et part des surcoûts, (S, K) chacune."""
    d = ctx.draws
    obs = ctx.observed_regime
    pop = union.population * d.population[:, None]
    share = pop / pop.sum(axis=1, keepdims=True)

    def access(r: ConstitutionalRegime, infra: np.ndarray) -> np.ndarray:
        integ = np.minimum(1.0, r.market_rules.market_integration * infra)[:, None]
        return np.asarray(share + (1.0 - share) * integ)

    ma_ratio = access(regime, d.market_access) / access(obs, np.ones_like(d.market_access))
    revenue = union.revenue * (d.population * d.economy)[:, None] * ma_ratio ** gamma[:, None]

    transfers = union_transfers(revenue, pop, regime)

    f_admin, f_sec = ctx.overhead[:, 0:1], ctx.overhead[:, 1:2] * d.security[:, None]
    c = regime.defence_rules.common_defence_share
    overhead = f_admin + (1.0 - c) * f_sec + c * f_sec * share

    climate = d.climate if d.climate is not None else np.ones_like(d.population)
    infra = (1.0 - delta * regime.infrastructure_rules.common_infrastructure_share) / (
        1.0 - delta * obs.infrastructure_rules.common_infrastructure_share)
    cost = union.service_cost * (d.population * climate * d.urbanization * infra)[:, None]
    return (revenue + transfers - overhead) / cost, transfers / cost, overhead / cost


def _status(cov: np.ndarray, t: ViabilityThresholds) -> tuple[ViabilityStatus, float]:
    p_short = float(np.mean(cov < t.service_coverage_min))
    if p_short <= t.shortfall_probability_max:
        return ViabilityStatus.VIABLE, p_short
    if 1.0 - p_short <= t.shortfall_probability_max:
        return ViabilityStatus.NOT_VIABLE, p_short
    return ViabilityStatus.UNCERTAIN, p_short


def compute_viability(territory: Territory, regime: ConstitutionalRegime, scenario: Scenario,
                      context: ViabilityContext) -> ViabilityAssessment:
    if scenario.diagnostic_only:
        raise ValueError(f"{scenario.scenario_id} (S2C) : diagnostic agrégé, aucune viabilité évaluée")
    rid, sid = regime.regime_id.value, scenario.scenario_id
    union = context.union
    if union is None:
        return ViabilityAssessment(territory.territory_id, rid, sid, ViabilityStatus.UNKNOWN,
                                   None, None, None, None, False)
    unknown = [a.effect_key for a in context.effects if not a.known]
    if unknown:
        # Effet inconnu ≠ effet nul : sans γ ou δ, la couverture n'est pas calculable hors régime d'observation.
        return ViabilityAssessment(territory.territory_id, rid, sid, ViabilityStatus.UNKNOWN,
                                   None, None, None, None, False)
    k = union.index(territory)
    gamma, delta = context.exploratory[:, 0], context.exploratory[:, 1]
    cov, tr, ov = _coverage(union, regime, context, gamma, delta)
    status, p_short = _status(cov[:, k], context.thresholds)
    g_iv, d_iv = (a.interval() for a in context.effects)
    bounds = []
    for g, dl in ((g_iv.lo, d_iv.lo), (g_iv.hi, d_iv.hi)):
        c_b = _coverage(union, regime, context, np.full_like(gamma, g), np.full_like(delta, dl))[0]
        bounds.append(_status(c_b[:, k], context.thresholds)[0])
    return ViabilityAssessment(
        territory.territory_id, rid, sid, status, UncertainValue.from_samples(cov[:, k]), p_short,
        UncertainValue.from_samples(tr[:, k]), UncertainValue.from_samples(ov[:, k]),
        exploratory_dependency=any(b is not status for b in bounds))


def draw_model(model: ViabilityManifest, effects: tuple[CausalAnswer, CausalAnswer], n: int,
               seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Tirages des effets (γ, δ) issus de la bibliothèque gelée, et des surcoûts (F_admin, F_sec).

    Un effet inconnu donne des tirages NaN : ``compute_viability`` rend alors UNKNOWN.
    """
    from amtgo.utils.canonical import sha256_hex

    rng = np.random.default_rng([seed, int(sha256_hex(model.content_hash)[:12], 16)])
    o = model.sovereign_overhead
    exploratory = np.column_stack([a.draws(n, rng) if a.known else np.full(n, np.nan) for a in effects])
    overhead = np.column_stack([o.administration.sample(rng, n), o.security.sample(rng, n)])
    return exploratory, overhead
