"""Compétences, règles de décision et garde-fous (prompt §22, 02 §7, 01 §30).

Une politique est un **vecteur de compétences**, jamais une étiquette
(« autonomie », « fédéralisme » ne sont pas des traitements primitifs).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Domain(StrEnum):
    """Domaines de domination (prompt §22)."""

    CIVIL_JUSTICE = "civil_justice"
    POLITICAL_VOICE = "political_voice"
    EXECUTIVE_POWER = "executive_power"
    SECURITY = "security"
    PUBLIC_EMPLOYMENT = "public_employment"
    PUBLIC_SERVICES = "public_services"
    LAND = "land"
    RESOURCES = "resources"
    CULTURE_LANGUAGE = "culture_language"
    LOCAL_GOVERNMENT = "local_government"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DecisionRule(_Strict):
    """Règle de décision d'une institution pour un domaine.

    Le pouvoir effectif d'un groupe de représentation r est :
    - avec veto : 1 ;
    - sinon : min(1, r / (1 − q)) où q est le seuil d'adoption — il faut
      détenir plus de 1 − q pour bloquer, plus de q pour décider seul.
    """

    threshold: float = Field(ge=0.5, lt=1.0)  # 0,5 = majorité simple
    veto_groups: tuple[str, ...] = ()

    def power(self, group: str, representation: float) -> float:
        if group in self.veto_groups:
            return 1.0
        return min(1.0, representation / (1.0 - self.threshold))


class CompetenceVector(_Strict):
    """A_{k,d} ∈ [0,1] : part de l'autorité sur le domaine d détenue par la juridiction k.

    Invariant §84 : pour une compétence exclusive, la somme sur les niveaux qui la
    partagent vaut 1 (vérifié par ``check_exclusive``).
    """

    authority: dict[Domain, float]

    @model_validator(mode="after")
    def _unit(self) -> Self:
        for d, a in self.authority.items():
            if not 0.0 <= a <= 1.0:
                raise ValueError(f"autorité {d.value} hors [0,1]")
        return self

    def get(self, d: Domain) -> float:
        return self.authority.get(d, 0.0)


def check_exclusive(vectors: list[CompetenceVector], domains: list[Domain], tol: float = 1e-9) -> None:
    for d in domains:
        total = sum(v.get(d) for v in vectors)
        if abs(total - 1.0) > tol:
            raise ValueError(f"compétence exclusive {d.value} : Σ_λ A = {total:.6f} ≠ 1 (prompt §84)")


class RightsProfile(_Strict):
    """C_{k,d} ∈ [0,1] : garde-fous effectifs (juridiction indépendante, droits des minorités…)."""

    checks: dict[Domain, float]
    default: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _unit(self) -> Self:
        for d, c in self.checks.items():
            if not 0.0 <= c <= 1.0:
                raise ValueError(f"garde-fou {d.value} hors [0,1]")
        return self

    def get(self, d: Domain) -> float:
        return self.checks.get(d, self.default)


class Representation(_Strict):
    """Représentation d'un groupe dans les organes d'une juridiction.

    ``proportional`` : représentation = part de population du groupe dans la juridiction.
    ``excluded`` : groupes exclus d'un domaine (représentation nulle), cas du monde E.
    ``fixed`` : représentations observées, prioritaires.
    """

    rule: str = Field(pattern=r"^(proportional|fixed)$")
    excluded: dict[Domain, tuple[str, ...]] = Field(default_factory=dict)
    fixed: dict[Domain, dict[str, float]] = Field(default_factory=dict)


class Institution(_Strict):
    jurisdiction_id: str
    level: str
    competences: CompetenceVector
    decision: dict[Domain, DecisionRule]
    default_decision: DecisionRule
    rights: RightsProfile
    representation: Representation

    def rule(self, d: Domain) -> DecisionRule:
        return self.decision.get(d, self.default_decision)
