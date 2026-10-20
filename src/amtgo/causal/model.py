"""Effets causaux : traitement, résultat, design, grade, transport (prompt §31, 04, schéma 10 §14).

Règle fondamentale : P(Y | A) ≠ P(Y | do(A)). Un enregistrement porte son grade
d'identification ; le grade ne peut pas dépasser le plafond de son design, et
les grades I1–I4 exigent que tous les diagnostics du design soient passés — un
diagnostic échoué n'est jamais ignoré, il rend l'effet inadmissible.

Admissibilité d'un effet pour un contexte cible :

- ``CAUSAL_FACT`` : I1–I5, transport IDENTIFIED, recouvrement ≥ τ_O ;
- ``BOUNDED`` : identification partielle (I6) ou transport PARTIAL — le solveur
  ne voit que des bornes (04 §11) ;
- ``EXPLORATORY_ONLY`` : I7, hypothèse d'expert ; jamais un fait causal ;
- ``UNSUPPORTED`` : diagnostics échoués, transport non soutenu, recouvrement
  insuffisant, ou politique trop loin du support → CAUSAL_EFFECT_UNKNOWN.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.core.uncertainty import DistributionType, UncertainValue
from amtgo.scenarios.model import Interval
from amtgo.utils.canonical import content_hash, stable_uuid

CAUSAL_EFFECT_UNKNOWN = "CAUSAL_EFFECT_UNKNOWN"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IdentificationGrade(StrEnum):
    """Hiérarchie d'identification (04 §5). I1 le plus fort."""

    I1 = "I1"  # randomisé
    I2 = "I2"  # expérience naturelle / RD valide
    I3 = "I3"  # DiD échelonné robuste
    I4 = "I4"  # contrôle synthétique / comparatif
    I5 = "I5"  # observationnel, échangeabilité explicite
    I6 = "I6"  # structurel / identification partielle
    I7 = "I7"  # hypothèse d'expert

    @property
    def rank(self) -> int:
        return int(self.value[1])


class Design(StrEnum):
    RANDOMIZED = "randomized"
    NATURAL_EXPERIMENT = "natural_experiment"
    GEOGRAPHIC_RD = "geographic_rd"
    STAGGERED_DID = "staggered_did"
    SYNTHETIC_CONTROL = "synthetic_control"
    OBSERVATIONAL = "observational"
    PARTIAL_IDENTIFICATION = "partial_identification"
    EXPERT_HYPOTHESIS = "expert_hypothesis"


# Grade maximal atteignable par design (04 §5).
DESIGN_CEILING: dict[Design, IdentificationGrade] = {
    Design.RANDOMIZED: IdentificationGrade.I1,
    Design.NATURAL_EXPERIMENT: IdentificationGrade.I2,
    Design.GEOGRAPHIC_RD: IdentificationGrade.I2,
    Design.STAGGERED_DID: IdentificationGrade.I3,
    Design.SYNTHETIC_CONTROL: IdentificationGrade.I4,
    Design.OBSERVATIONAL: IdentificationGrade.I5,
    Design.PARTIAL_IDENTIFICATION: IdentificationGrade.I6,
    Design.EXPERT_HYPOTHESIS: IdentificationGrade.I7,
}

# Diagnostics exigés par design (04 §6-8).
REQUIRED_DIAGNOSTICS: dict[Design, tuple[str, ...]] = {
    Design.STAGGERED_DID: ("pre_trends", "anticipation", "composition", "spillovers", "endogenous_adoption"),
    Design.GEOGRAPHIC_RD: ("treatment_discontinuity", "baseline_continuity", "sorting", "other_breaks"),
    Design.SYNTHETIC_CONTROL: ("pre_fit", "donor_pool", "contamination", "placebos", "sensitivity"),
}


class Diagnostic(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_TESTED = "NOT_TESTED"


class TreatmentComponent(StrEnum):
    """Composantes du vecteur de traitement (04 §2).

    « autonomy » et « federalism » ne sont pas des traitements primitifs (02 §7) :
    ce sont des bundles de compétences, refusés ici. La souveraineté est un bundle
    décomposé en composantes (04 §15).
    """

    REPRESENTATION = "rep"
    LANGUAGE = "lang"
    FISCAL = "fisc"
    LAND = "land"
    POLICE = "police"
    JUSTICE = "justice"
    MOBILITY = "mobility"
    RESOURCES = "resources"
    MARKET_ACCESS = "market_access"
    INFRASTRUCTURE = "infrastructure"
    INSTITUTIONALIZATION = "institutionalization"  # institutionnalisation d'une identité (04 §16)
    SOVEREIGNTY = "sovereignty"


class OutcomeKind(StrEnum):
    """Résultats (04 §3)."""

    D = "D"
    F = "F"
    I = "I"  # noqa: E741
    V = "V"
    ECONOMY = "economy"
    MOBILITY = "mobility"
    IDENTITY = "identity"
    SALIENCE = "salience"
    RISK = "risk"


class TransportStatus(StrEnum):
    IDENTIFIED = "IDENTIFIED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"


class Admissibility(StrEnum):
    CAUSAL_FACT = "CAUSAL_FACT"
    BOUNDED = "BOUNDED"
    EXPLORATORY_ONLY = "EXPLORATORY_ONLY"
    UNSUPPORTED = "UNSUPPORTED"


class Treatment(_Strict):
    component: TreatmentComponent
    definition: str
    intensity_support: Interval  # intensités observées dans le contexte source
    version: str = "1"
    bundle: tuple[TreatmentComponent, ...] = ()  # souveraineté : composantes testées d'abord

    @model_validator(mode="after")
    def _bundle(self) -> Self:
        if self.component is TreatmentComponent.SOVEREIGNTY and not self.bundle:
            raise ValueError("souveraineté : bundle de composantes obligatoire (04 §15)")
        if self.component is not TreatmentComponent.SOVEREIGNTY and self.bundle:
            raise ValueError("seule la souveraineté est un bundle")
        return self


class Outcome(_Strict):
    kind: OutcomeKind
    variable: str
    unit: str


class CausalEffect(_Strict):
    """Enregistrement de la bibliothèque (04 §12, schéma 10 §14). Immuable dans une release."""

    effect_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    treatment: Treatment
    outcome: Outcome
    source_context: str
    target_context: str
    estimand: str  # ATT, ATE, LATE, bounds…
    design: Design
    grade: IdentificationGrade
    effect: UncertainValue  # tirages, ou bornes seules
    time_horizon_years: float = Field(gt=0)
    spillover_model: str
    mechanism: str
    transport_status: TransportStatus
    overlap: float = Field(ge=0.0, le=1.0)
    diagnostics: dict[str, Diagnostic] = Field(default_factory=dict)
    robustness: dict[str, str] = Field(default_factory=dict)
    source_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ceiling = DESIGN_CEILING[self.design]
        if self.grade.rank < ceiling.rank:
            raise ValueError(f"{self.effect_key} : grade {self.grade} au-dessus du plafond {ceiling} de {self.design}")
        if self.grade.rank <= 4:
            required = REQUIRED_DIAGNOSTICS.get(self.design, ())
            missing = [d for d in required if self.diagnostics.get(d) is not Diagnostic.PASSED]
            if missing and not self.diagnostics_failed:
                raise ValueError(f"{self.effect_key} : grade {self.grade} sans diagnostics passés : {missing}")
        if self.grade in (IdentificationGrade.I6, IdentificationGrade.I7) and self.effect.has_samples:
            raise ValueError(f"{self.effect_key} : {self.grade} ne porte que des bornes, jamais une loi")
        if self.effect.lower is None or self.effect.upper is None:
            raise ValueError(f"{self.effect_key} : bornes de l'effet obligatoires")
        return self

    @property
    def diagnostics_failed(self) -> bool:
        return any(v is Diagnostic.FAILED for v in self.diagnostics.values())

    @property
    def effect_id(self) -> str:
        return str(stable_uuid("causal_effect", self.model_dump(mode="json")))

    @property
    def content_hash(self) -> str:
        return content_hash(self)

    def admissibility(self, overlap_min: float) -> Admissibility:
        if self.diagnostics_failed or self.transport_status is TransportStatus.UNSUPPORTED \
                or self.overlap < overlap_min:
            return Admissibility.UNSUPPORTED
        if self.grade is IdentificationGrade.I7:
            return Admissibility.EXPLORATORY_ONLY
        if self.grade is IdentificationGrade.I6 or self.transport_status is TransportStatus.PARTIAL:
            return Admissibility.BOUNDED
        return Admissibility.CAUSAL_FACT


def support_distance(intensity: float, support: Interval) -> float:
    """d_A (04 §14) : distance relative hors du support observé (0 dans le support)."""
    width = max(support.hi - support.lo, 1e-12)
    if support.lo <= intensity <= support.hi:
        return 0.0
    return (support.lo - intensity if intensity < support.lo else intensity - support.hi) / width


def widen(effect: UncertainValue, factor: float) -> UncertainValue:
    """Bornes élargies autour du centre (U_novel, transport partiel) : la loi n'est plus identifiée."""
    lo, hi = effect.lower, effect.upper
    assert lo is not None and hi is not None
    centre, half = (lo + hi) / 2.0, (hi - lo) / 2.0 * factor
    return UncertainValue.bounds(centre - half, centre + half)


def sovereignty_residual(total: np.ndarray, components: list[np.ndarray],
                         interactions: np.ndarray | None = None) -> UncertainValue:
    """τ_S^res = τ_S^total − Σ τ_components − interactions (04 §15), par tirage."""
    res = total - np.sum(components, axis=0) - (0.0 if interactions is None else interactions)
    return UncertainValue.from_samples(res)


def is_bounds_only(u: UncertainValue) -> bool:
    return u.distribution_type in (DistributionType.UNKNOWN, DistributionType.UNIFORM) and not u.has_samples
