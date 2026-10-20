"""ViabilityManifest : paramètres du modèle de viabilité contextuelle (M6), figés dans le RunManifest."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from amtgo.scenarios.model import Interval
from amtgo.utils.canonical import content_hash


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SovereignOverhead(_Strict):
    """Coûts fixes annuels d'une juridiction souveraine (unités monétaires du jeu fiscal), PROVISOIRES."""

    administration: Interval
    security: Interval


class ViabilityEffects(_Strict):
    """Clés des effets dans la bibliothèque causale gelée (M7) — jamais des coefficients en dur.

    Toute conclusion qui change entre les bornes d'un effet non identifié est
    signalée « dépend des bornes d'effets non identifiés ».
    """

    market_access_elasticity: str  # élasticité de la base fiscale à l'accès au marché
    infrastructure_cost_reduction: str  # baisse du coût des services par infrastructure commune


class ViabilityManifest(_Strict):
    model_id: str
    version: str
    description: str
    fiscal_source: str
    revenue_variable: str
    cost_variable: str
    # Régime sous lequel les comptes fiscaux sont observés : hypothèse déclarée.
    observed_regime: str
    # Régimes évalués en plus du régime du run (sensibilité au régime, 05 §19).
    regime_sensitivity: tuple[str, ...] = Field(min_length=1)
    level: str  # niveau du statu quo évalué (juridictions souveraines)
    sovereign_overhead: SovereignOverhead
    effects: ViabilityEffects
    # Hypothèse de clôture : l'union qui transfère et mutualise est la région analysée.
    union_closure: str

    @property
    def content_hash(self) -> str:
        return content_hash(self)
