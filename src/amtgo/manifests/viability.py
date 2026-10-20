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


class ExploratoryEffects(_Strict):
    """Coefficients NON CAUSAUX (grade I7) : bornes larges incluant l'effet nul (prompt §33).

    Ils seront remplacés par la bibliothèque causale (M7). Toute conclusion qui
    change entre leurs bornes est signalée « dépend de coefficients exploratoires ».
    """

    market_access_elasticity: Interval  # élasticité de la base fiscale à l'accès au marché
    infrastructure_cost_reduction: Interval  # baisse du coût des services par infrastructure commune
    source: str


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
    exploratory: ExploratoryEffects
    # Hypothèse de clôture : l'union qui transfère et mutualise est la région analysée.
    union_closure: str

    @property
    def content_hash(self) -> str:
        return content_hash(self)
