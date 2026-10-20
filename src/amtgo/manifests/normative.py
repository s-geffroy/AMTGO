"""NormativeManifest : tous les paramètres normatifs, jamais en dur (prompt §59, 06 §5).

Certains invariants ne sont *pas* des paramètres : un manifeste qui les violerait
est refusé au chargement (prompt §86). Ce n'est pas une préférence du code, c'est
la doctrine V1.0-RC1 :

- le modèle n'infère jamais un consentement final ;
- les hard rights ne sont pas relaxables ;
- l'export public par défaut n'est pas PUBLIC ;
- aucune pénalité abstraite au nombre d'États.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.core.enums import PrivacyClass
from amtgo.utils.canonical import content_hash


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HardRight(_Strict):
    right_id: str
    description: str
    relaxable: bool = False

    @model_validator(mode="after")
    def _not_relaxable(self) -> Self:
        if self.relaxable:
            raise ValueError(f"hard right {self.right_id!r} déclaré relaxable : interdit (prompt §86)")
        return self


class RightsThresholds(_Strict):
    # P(d_gkd > τ_d) ≤ ε_d (02 §9)
    severe_domination_threshold: float = Field(ge=0.0, le=1.0)
    severe_domination_probability_max: float = Field(ge=0.0, le=1.0)
    # Exception d'urgence (02 §27) : P(D_grave > τ_urgent) > p_urgent
    urgent_domination_threshold: float = Field(ge=0.0, le=1.0)
    urgent_probability: float = Field(ge=0.0, le=1.0)


class StabilityThresholds(_Strict):
    scale_min: float = Field(ge=0.0, le=1.0)  # τ_scale
    publish_min: float = Field(ge=0.0, le=1.0)  # τ de S_publish
    overlap_min: float = Field(ge=0.0, le=1.0)  # τ_O (common support)


class RobustnessWeights(_Strict):
    # ρ(J) = E[J] + λ_tail CVaR_α(J) + λ_var Var(J)   (02 §18)
    cvar_alpha: float = Field(gt=0.0, lt=1.0)
    lambda_tail: float = Field(ge=0.0)
    lambda_var: float = Field(ge=0.0)


class OptimizationRules(_Strict):
    reification_penalty_enabled: bool
    state_count_penalty_enabled: bool = False
    # Ordre lexicographique optionnel : profil normatif versionné, pas vérité (01 §9).
    priority_profile: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _no_state_count(self) -> Self:
        if self.state_count_penalty_enabled:
            raise ValueError("pénalité abstraite au nombre d'États interdite (prompt §42)")
        return self


class ConsentRules(_Strict):
    model_may_infer_final_consent: bool = False

    @model_validator(mode="after")
    def _never_infer(self) -> Self:
        if self.model_may_infer_final_consent:
            raise ValueError("le modèle ne peut jamais inférer un consentement final (prompt §30)")
        return self


class PrivacyRules(_Strict):
    default_access: PrivacyClass = PrivacyClass.CONTROLLED

    @model_validator(mode="after")
    def _not_public_by_default(self) -> Self:
        if self.default_access is PrivacyClass.PUBLIC:
            raise ValueError("l'accès par défaut ne peut pas être PUBLIC (prompt §50, §86)")
        return self


class NormativeManifest(_Strict):
    manifest_id: str
    version: str
    description: str
    hard_rights: tuple[HardRight, ...]
    rights: RightsThresholds
    stability: StabilityThresholds
    robustness: RobustnessWeights
    optimization: OptimizationRules
    consent: ConsentRules
    privacy: PrivacyRules

    @property
    def content_hash(self) -> str:
        return content_hash(self)
