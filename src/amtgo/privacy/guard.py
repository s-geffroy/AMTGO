"""Privacy guard (prompt §49) — version minimale M2, complétée en M11.

Toute couche exportée passe par ``evaluate`` (prompt §49), qui renvoie
allow / aggregate / suppress / restrict. Cette version ne laisse sortir en
PUBLIC que des couches **sans aucune donnée de population ni de groupe** (fonds
de carte, maillages, statuts). Tout le reste est restreint, faute d'un modèle de
menace (03 §25 : pas de seuil universel). Le risque couvre l'individu, le
groupe et le mésusage politique (06 §10).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from amtgo.core.enums import PrivacyClass
from amtgo.errors import PrivacyViolation


class PrivacyAction(StrEnum):
    ALLOW = "allow"
    AGGREGATE = "aggregate"
    SUPPRESS = "suppress"
    RESTRICT = "restrict"


@dataclass(frozen=True)
class ExportLayer:
    name: str
    privacy_class: PrivacyClass
    contains_population: bool
    contains_group_attributes: bool
    contains_mobility: bool
    feature_count: int


@dataclass(frozen=True)
class PrivacyDecision:
    action: PrivacyAction
    reason: str


def evaluate(layer: ExportLayer, target: PrivacyClass = PrivacyClass.PUBLIC) -> PrivacyDecision:
    if layer.privacy_class is PrivacyClass.PROHIBITED:
        return PrivacyDecision(PrivacyAction.SUPPRESS, "classe PROHIBITED")
    if layer.contains_group_attributes or layer.contains_mobility:
        # Group privacy : aucun modèle de menace validé avant M11.
        return PrivacyDecision(PrivacyAction.RESTRICT, "attributs de groupe ou mobilité")
    if layer.contains_population and target is PrivacyClass.PUBLIC:
        return PrivacyDecision(PrivacyAction.AGGREGATE, "population : agrégation requise avant export public")
    if layer.privacy_class.rank > target.rank:
        return PrivacyDecision(PrivacyAction.RESTRICT, f"classe {layer.privacy_class.value} > cible {target.value}")
    return PrivacyDecision(PrivacyAction.ALLOW, "couche sans donnée de population ni de groupe")


def require_allowed(layer: ExportLayer, target: PrivacyClass = PrivacyClass.PUBLIC) -> None:
    decision = evaluate(layer, target)
    if decision.action is not PrivacyAction.ALLOW:
        raise PrivacyViolation(f"export de {layer.name!r} refusé ({decision.action.value}) : {decision.reason}")
