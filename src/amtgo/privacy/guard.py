"""Privacy guard (prompt §49) — version minimale M2, complétée en M11.

Toute couche exportée passe par ``evaluate`` (prompt §49), qui renvoie
allow / aggregate / suppress / restrict. Ne sortent en PUBLIC que des couches
**sans aucune donnée de population ni de groupe** (fonds de carte, maillages,
statuts). Le risque couvre l'individu, le groupe et le mésusage politique
(06 §10).

M11 ajoute l'évaluation d'une **publication entière** (``evaluate_release``),
parce qu'une couche anodine seule peut ne plus l'être à côté d'une autre
(05 §15) :

- petit effectif : un comptage inférieur à k (modèle de menace, manifeste
  normatif ; 03 §25 : pas de seuil universel) est supprimé ;
- différenciation : un même comptage publié sur deux supports différents
  permet d'isoler leur différence — seul le premier support peut sortir ;
- inférence : un attribut déclaré proxy d'un attribut sensible (religion,
  langue, étiquette historique, route) est restreint ;
- dérivation : une géométrie calculée à partir des parts de groupes (frontière
  candidate) révèle la distribution des groupes — restreinte ;
- routes et mobilités : restreintes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

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
    attributes: tuple[str, ...] = ()
    support: str = ""  # maillage ou partition de la couche
    min_count: float | None = None  # plus petit comptage non nul publié (None : aucun comptage)
    derived_from_group_attributes: bool = False


@dataclass(frozen=True)
class PrivacyDecision:
    action: PrivacyAction
    reason: str

    @property
    def released(self) -> bool:
        return self.action is PrivacyAction.ALLOW


class ReleaseRules(Protocol):
    @property
    def min_group_count(self) -> int: ...
    @property
    def sensitive_proxies(self) -> tuple[str, ...]: ...


def evaluate(layer: ExportLayer, target: PrivacyClass = PrivacyClass.PUBLIC) -> PrivacyDecision:
    if layer.privacy_class is PrivacyClass.PROHIBITED:
        return PrivacyDecision(PrivacyAction.SUPPRESS, "classe PROHIBITED")
    if layer.contains_group_attributes or layer.contains_mobility:
        return PrivacyDecision(PrivacyAction.RESTRICT, "attributs de groupe ou mobilité")
    if layer.derived_from_group_attributes:
        return PrivacyDecision(PrivacyAction.RESTRICT, "géométrie dérivée des parts de groupes")
    if layer.contains_population and target is PrivacyClass.PUBLIC:
        return PrivacyDecision(PrivacyAction.AGGREGATE, "population : agrégation requise avant export public")
    if layer.privacy_class.rank > target.rank:
        return PrivacyDecision(PrivacyAction.RESTRICT, f"classe {layer.privacy_class.value} > cible {target.value}")
    return PrivacyDecision(PrivacyAction.ALLOW, "couche sans donnée de population ni de groupe")


def evaluate_release(layers: list[ExportLayer], rules: ReleaseRules,
                     target: PrivacyClass = PrivacyClass.PUBLIC) -> dict[str, PrivacyDecision]:
    """Décision par couche d'une publication entière (couches dans l'ordre de priorité)."""
    out: dict[str, PrivacyDecision] = {}
    counted: dict[str, str] = {}  # attribut compté → premier support publié
    for layer in layers:
        d = evaluate(layer, target)
        passing = d.action in (PrivacyAction.ALLOW, PrivacyAction.AGGREGATE)
        if passing and layer.min_count is not None and layer.min_count < rules.min_group_count:
            d = PrivacyDecision(PrivacyAction.SUPPRESS, f"comptage < k={rules.min_group_count} (petit effectif)")
        elif passing and set(layer.attributes) & set(rules.sensitive_proxies):
            proxies = sorted(set(layer.attributes) & set(rules.sensitive_proxies))
            d = PrivacyDecision(PrivacyAction.RESTRICT, f"inférence d'attribut sensible via {proxies}")
        elif passing and layer.min_count is not None:
            clash = sorted(a for a in layer.attributes if counted.get(a, layer.support) != layer.support)
            if clash:
                d = PrivacyDecision(PrivacyAction.RESTRICT,
                                    f"différenciation : {clash} déjà publié(s) sur {counted[clash[0]]}")
            else:
                for a in layer.attributes:
                    counted.setdefault(a, layer.support)
        out[layer.name] = d
    return out


def require_allowed(layer: ExportLayer, target: PrivacyClass = PrivacyClass.PUBLIC) -> None:
    decision = evaluate(layer, target)
    if decision.action is not PrivacyAction.ALLOW:
        raise PrivacyViolation(f"export de {layer.name!r} refusé ({decision.action.value}) : {decision.reason}")
