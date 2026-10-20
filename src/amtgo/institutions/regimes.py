"""Régimes constitutionnels exogènes (prompt §28, spec 14).

Le contenu est entièrement piloté par ``configs/regimes/*.yaml`` ; le code ne
fixe que la structure et les noms canoniques (ADR-0003). R3 est un scénario,
pas la doctrine du modèle.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from amtgo.config.loader import load_model
from amtgo.errors import ConfigurationError
from amtgo.utils.canonical import content_hash


class RegimeId(StrEnum):
    R0_CURRENT_LIKE = "R0_CURRENT_LIKE"
    R1_COMMON_MARKET = "R1_COMMON_MARKET"
    R2_CONFEDERAL = "R2_CONFEDERAL"
    R3_FEDERAL_CONTINENTAL = "R3_FEDERAL_CONTINENTAL"


# Noms utilisés ailleurs dans le corpus (01 §5, 02 §5) : acceptés, normalisés.
REGIME_ALIASES: dict[str, RegimeId] = {
    "R0": RegimeId.R0_CURRENT_LIKE,
    "R0_CURRENT": RegimeId.R0_CURRENT_LIKE,
    "R1": RegimeId.R1_COMMON_MARKET,
    "R2": RegimeId.R2_CONFEDERAL,
    "R2_CONFEDERATION": RegimeId.R2_CONFEDERAL,
    "R3": RegimeId.R3_FEDERAL_CONTINENTAL,
    "R3_FEDERAL": RegimeId.R3_FEDERAL_CONTINENTAL,
}


def normalize_regime_id(name: str) -> RegimeId:
    key = name.strip().upper()
    if key in RegimeId.__members__:
        return RegimeId[key]
    if key in REGIME_ALIASES:
        return REGIME_ALIASES[key]
    raise ConfigurationError(f"régime constitutionnel inconnu : {name!r}")


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


_Unit = Annotated[float, Field(ge=0.0, le=1.0)]


class MobilityRules(_Strict):
    free_movement: _Unit  # 1 : libre circulation complète entre États
    cross_border_recognition: bool = False


class FiscalTransferRules(_Strict):
    # Part de l'écart de capacité fiscale par habitant (sous la moyenne de l'union) comblée.
    equalization_rate: _Unit
    # Part des recettes mise en commun et redistribuée par habitant (fiscalité partagée).
    pooled_revenue_share: _Unit = 0.0


class DefenceRules(_Strict):
    # Part du coût fixe de sécurité mutualisée au niveau de l'union.
    common_defence_share: _Unit
    security_coordination: bool = False


class MarketRules(_Strict):
    market_integration: _Unit  # 1 : marché commun complet
    constitutional_arbitration: bool = False


class ResourceRules(_Strict):
    shared_resource_share: _Unit


class InfrastructureRules(_Strict):
    common_infrastructure_share: _Unit


class DeclaredBorder(_Strict):
    """Dimensions de frontière non dérivables des règles : politique et culturelle (PROVISOIRES)."""

    P: _Unit
    C: _Unit


class ConstitutionalRegime(_Strict):
    """Schéma 10 §16, règles typées (M6, ADR-0018).

    Les dimensions E, M, R, S de la frontière entre États **dérivent** des règles
    (σ^M = 1 − libre circulation, etc.) : un régime ne peut pas déclarer un marché
    commun complet et une frontière économique forte. P et C sont déclarées.
    ``infrastructure_rules`` étend le schéma 10 §16 : 02 §14 rend la viabilité
    dépendante de l'infrastructure sous le régime.
    """

    regime_id: RegimeId
    name: str
    version: str
    description: str
    mobility_rules: MobilityRules
    fiscal_transfer_rules: FiscalTransferRules
    defence_rules: DefenceRules
    market_rules: MarketRules
    resource_rules: ResourceRules
    infrastructure_rules: InfrastructureRules
    declared_border: DeclaredBorder

    @property
    def border_template(self) -> dict[str, float]:
        """Gabarit σ entre deux États sous ce régime (dimensions de ``BorderDim``)."""
        # Arrondi : 1 − 0,9 doit valoir 0,1, pas 0,09999999999999998 (empreintes stables).
        return {
            "P": self.declared_border.P,
            "C": self.declared_border.C,
            "E": round(1.0 - self.market_rules.market_integration, 12),
            "M": round(1.0 - self.mobility_rules.free_movement, 12),
            "R": round(1.0 - self.resource_rules.shared_resource_share, 12),
            "S": round(1.0 - self.defence_rules.common_defence_share, 12),
        }

    @property
    def content_hash(self) -> str:
        return content_hash(self)


def load_regime(configs_dir: Path, name: str) -> ConstitutionalRegime:
    rid = normalize_regime_id(name)
    regime = load_model(ConstitutionalRegime, configs_dir / "regimes" / f"{rid.value}.yaml")
    if regime.regime_id is not rid:
        raise ConfigurationError(f"{rid.value}.yaml déclare {regime.regime_id.value}")
    return regime
