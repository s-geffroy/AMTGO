"""Régimes constitutionnels exogènes (prompt §28, spec 14).

Le contenu est entièrement piloté par ``configs/regimes/*.yaml`` ; le code ne
fixe que la structure et les noms canoniques (ADR-0003). R3 est un scénario,
pas la doctrine du modèle.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

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


class ConstitutionalRegime(BaseModel):
    """Schéma 10 §16. Les règles restent des mappings déclaratifs à ce stade (M6 les typera)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    regime_id: RegimeId
    name: str
    version: str
    description: str
    mobility_rules: dict[str, Any]
    fiscal_transfer_rules: dict[str, Any]
    defence_rules: dict[str, Any]
    market_rules: dict[str, Any]
    resource_rules: dict[str, Any]
    # Gabarit de frontière entre États sous ce régime (σ par dimension, PROVISOIRE) : un marché
    # commun abaisse σ^E et σ^M, une défense commune σ^S, etc. (01 §5).
    border_template: dict[str, float]

    @property
    def content_hash(self) -> str:
        return content_hash(self)


def load_regime(configs_dir: Path, name: str) -> ConstitutionalRegime:
    rid = normalize_regime_id(name)
    regime = load_model(ConstitutionalRegime, configs_dir / "regimes" / f"{rid.value}.yaml")
    if regime.regime_id is not rid:
        raise ConfigurationError(f"{rid.value}.yaml déclare {regime.regime_id.value}")
    return regime
