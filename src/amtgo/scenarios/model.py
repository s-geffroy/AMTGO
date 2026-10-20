"""Scénarios versionnés (prompt §34-37, 02 §23-25, schéma 10 §17).

Un scénario fixe les axes exogènes (population, climat, urbanisation, économie,
migration, infrastructure, sécurité) et le **régime de mobilité** :

- S1 : aucun déplacement induit (m^reform = 0) ;
- S2A : mobilité volontaire uniquement (m^forced = 0) ; la réponse volontaire à
  une réforme est un effet causal (M7) : sans lui, CAUSAL_EFFECT_UNKNOWN ;
- S2C : diagnostic agrégé de dépendance à la coercition, jamais un plan.

Les déplacements forcés ne sont pas un paramètre : ``forced_migration`` et
``reform_induced_relocation`` existent pour être vérifiés nuls (garde-fou §35),
au chargement et à l'exécution. Chaque axe est un intervalle déclaré ; un
intervalle réduit à un point est une hypothèse de maintien, déclarée comme telle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.errors import NormativeViolation
from amtgo.utils.canonical import content_hash, sha256_hex


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MobilityRegime(StrEnum):
    S1 = "S1"
    S2A = "S2A"
    S2C = "S2C"


class Interval(_Strict):
    lo: float
    hi: float

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.lo > self.hi:
            raise ValueError(f"intervalle [{self.lo}, {self.hi}] inversé")
        return self

    @property
    def is_point(self) -> bool:
        return self.lo == self.hi

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        return rng.uniform(self.lo, self.hi, n) if not self.is_point else np.full(n, self.lo)


class PopulationAxis(_Strict):
    annual_growth: Interval  # croissance naturelle, uniforme sur la région (hypothèse déclarée)


class EconomyAxis(_Strict):
    annual_fiscal_base_growth: Interval  # base fiscale réelle par habitant


class ClimateAxis(_Strict):
    """Multiplicateur du coût des services à l'horizon, par trajectoire climatique.

    Aucun scénario climatique unique (03 §14) : au moins deux trajectoires, ou
    ``modelled: false`` — le climat est alors reporté NON MODÉLISÉ, jamais neutre.
    """

    modelled: bool
    pathways: dict[str, Interval] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensemble(self) -> Self:
        if self.modelled and len(self.pathways) < 2:
            raise ValueError("climat : au moins deux trajectoires (aucun scénario climatique unique)")
        if not self.modelled and self.pathways:
            raise ValueError("climat non modélisé : aucune trajectoire attendue")
        return self


class UrbanizationAxis(_Strict):
    service_cost_multiplier: Interval  # effet de l'urbanisation sur le coût par habitant


class MigrationAxis(_Strict):
    # Solde migratoire exogène (hors réforme), uniforme sur la région : aucune allocation spatiale.
    exogenous_annual_net_rate: Interval
    forced_migration: float = 0.0
    reform_induced_relocation: float = 0.0
    # S2A : référence à une réponse volontaire de la bibliothèque causale (M7). None : inconnue.
    voluntary_response: str | None = None


class InfrastructureAxis(_Strict):
    market_access_multiplier: Interval  # ≥ 1 : investissement d'infrastructure


class SecurityAxis(_Strict):
    security_cost_multiplier: Interval


class Scenario(_Strict):
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    version: str
    description: str
    mobility_regime: MobilityRegime
    horizon_years: int = Field(gt=0, le=100)
    population: PopulationAxis
    climate: ClimateAxis
    urbanization: UrbanizationAxis
    economy: EconomyAxis
    migration: MigrationAxis
    infrastructure: InfrastructureAxis
    security: SecurityAxis

    @model_validator(mode="after")
    def _hard_guards(self) -> Self:
        m = self.migration
        if m.forced_migration != 0.0:
            raise ValueError("forced_migration doit valoir 0 : hard right no_forced_displacement (prompt §86)")
        if m.reform_induced_relocation != 0.0:
            raise ValueError("reform_induced_relocation doit valoir 0 : une relocalisation n'est jamais un "
                             "paramètre (S1 : nulle ; S2A : réponse volontaire causale uniquement)")
        if self.mobility_regime is MobilityRegime.S1 and m.voluntary_response is not None:
            raise ValueError("S1 : aucun déplacement induit, pas de réponse de mobilité à la réforme")
        if self.mobility_regime is MobilityRegime.S2C and m.voluntary_response is not None:
            raise ValueError("S2C : diagnostic agrégé uniquement, aucune réponse de mobilité modélisée")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)

    @property
    def diagnostic_only(self) -> bool:
        return self.mobility_regime is MobilityRegime.S2C

    def held_axes(self) -> list[str]:
        """Axes maintenus à leur valeur de référence (intervalle ponctuel) : hypothèses déclarées."""
        out = []
        for name, iv in [("population", self.population.annual_growth),
                         ("economy", self.economy.annual_fiscal_base_growth),
                         ("urbanization", self.urbanization.service_cost_multiplier),
                         ("migration", self.migration.exogenous_annual_net_rate),
                         ("infrastructure", self.infrastructure.market_access_multiplier),
                         ("security", self.security.security_cost_multiplier)]:
            if iv.is_point:
                out.append(name)
        return out


def assert_no_induced_displacement(scenario: Scenario, forced: float, induced: float | None) -> None:
    """Garde-fou d'exécution (prompt §35) : jamais de déplacement forcé, ni induit en S1."""
    if forced != 0.0:
        raise NormativeViolation(f"{scenario.scenario_id} : déplacement forcé {forced} ≠ 0")
    if scenario.mobility_regime is MobilityRegime.S1 and induced not in (0.0, None):
        raise NormativeViolation(f"{scenario.scenario_id} (S1) : relocalisation induite {induced} ≠ 0")
    if scenario.mobility_regime is MobilityRegime.S1 and induced is None:
        raise NormativeViolation(f"{scenario.scenario_id} (S1) : relocalisation induite non vérifiée")


@dataclass(frozen=True)
class ScenarioDraws:
    """Tirages des axes du scénario, un par tirage du champ de population (forme (S,))."""

    population: np.ndarray  # multiplicateur de population à l'horizon (croissance × solde migratoire)
    economy: np.ndarray  # multiplicateur de base fiscale par habitant
    climate: np.ndarray | None  # multiplicateur de coût ; None : climat non modélisé
    climate_pathway: np.ndarray | None  # indice de trajectoire par tirage
    urbanization: np.ndarray
    market_access: np.ndarray
    security: np.ndarray


def draw_scenario(scenario: Scenario, n: int, seed: int) -> ScenarioDraws:
    """Tirages déterministes : même scénario, même graine ⇒ mêmes tirages."""
    rng = np.random.default_rng([seed, int(sha256_hex(scenario.content_hash)[:12], 16)])
    t = scenario.horizon_years
    growth = (1.0 + scenario.population.annual_growth.sample(rng, n)) ** t
    migr = (1.0 + scenario.migration.exogenous_annual_net_rate.sample(rng, n)) ** t
    econ = (1.0 + scenario.economy.annual_fiscal_base_growth.sample(rng, n)) ** t
    climate = pathway = None
    if scenario.climate.modelled:
        names = sorted(scenario.climate.pathways)
        pathway = rng.integers(len(names), size=n)  # ensemble : trajectoires équiprobables (déclaré)
        climate = np.array([scenario.climate.pathways[names[k]].sample(rng, 1)[0] for k in pathway])
    return ScenarioDraws(
        population=growth * migr, economy=econ, climate=climate, climate_pathway=pathway,
        urbanization=scenario.urbanization.service_cost_multiplier.sample(rng, n),
        market_access=scenario.infrastructure.market_access_multiplier.sample(rng, n),
        security=scenario.security.security_cost_multiplier.sample(rng, n))
