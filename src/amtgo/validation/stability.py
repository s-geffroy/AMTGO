"""Stabilité et catégorie de publication (02 §19, 05 §18-21, prompt §45).

    S^publish = min(S^ontology, S^scale, S^time, S^parameter)

Une composante UNKNOWN rend S^publish UNKNOWN : on ne publie pas une frontière
dont on ignore la stabilité. Catégories (05 §21) :

- ``NOT_IDENTIFIABLE`` : S^publish inconnu, calculabilité D, ou dominance non
  résolue par un objectif inconnu ;
- ``DATA_LIMITED`` : calculabilité C ;
- ``EXPLORATORY`` : un gate applicable n'est pas passé, ou S^publish < τ ;
- ``CONDITIONAL`` : tout passe, mais la conclusion dépend d'un choix normatif
  (05 §18 : présentée comme choix politique) ou du régime constitutionnel (05 §19) ;
- ``ROBUST`` : sinon.

Pas de carte déterministe pour les deux premières (05 §21). Une publication
territoriale n'est permise qu'en ROBUST ou CONDITIONAL, tous gates passés (05 §20).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from amtgo.core.enums import ComputabilityClass, RecommendationStatus


def s_publish(components: Mapping[str, float | None]) -> float | None:
    vals = list(components.values())
    return None if any(v is None for v in vals) else min(vals)  # type: ignore[type-var]


def agreement(nominal: Mapping[str, tuple[bool, bool]], settings: Sequence[Mapping[str, tuple[bool, bool]]]
              ) -> dict[str, float | None]:
    """S^parameter par variante : part des réglages où (faisable, au front) est inchangé."""
    if not settings:
        return {k: None for k in nominal}
    return {k: sum(s.get(k) == v for s in settings) / len(settings) for k, v in nominal.items()}


def publication_category(gates: Mapping[str, str], s_pub: float | None, tau: float,
                         computability: ComputabilityClass, conclusion: str, political_choice: bool,
                         regime_dependent: bool) -> RecommendationStatus:
    unresolved = conclusion == "DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES"
    if s_pub is None or computability is ComputabilityClass.D or unresolved:
        return RecommendationStatus.NOT_IDENTIFIABLE
    if computability is ComputabilityClass.C:
        return RecommendationStatus.DATA_LIMITED
    if any(v != "PASSED" for v in gates.values()) or s_pub < tau:
        return RecommendationStatus.EXPLORATORY
    if political_choice or regime_dependent:
        return RecommendationStatus.CONDITIONAL
    return RecommendationStatus.ROBUST


def release_allowed(category: RecommendationStatus, gates: Mapping[str, str]) -> bool:
    return category in (RecommendationStatus.ROBUST, RecommendationStatus.CONDITIONAL) and all(
        v == "PASSED" for v in gates.values())
