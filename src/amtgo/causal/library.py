"""Bibliothèque causale : déclaration, estimation, gel, interrogation (prompt §31-33, 04 §12-14).

Deux origines d'enregistrements :

- **déclarés** : hypothèses d'expert (I7) ou bornes d'identification partielle
  (I6), saisies avec leur source ;
- **estimés** : produits dans le run par un design (DiD échelonné sur un panel),
  avec diagnostics et transport évalués vers le contexte cible.

Le gel (``causal_freeze``) a lieu après ``measurement_freeze`` et avant toute
évaluation qui consomme des effets. Ensuite, la bibliothèque est en lecture
seule : :class:`FrozenCausalLibrary` vérifie son empreinte au chargement et ne
fournit qu'une interrogation. Le solveur n'a aucun moyen d'ajuster un effet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.causal.model import (
    CAUSAL_EFFECT_UNKNOWN,
    Admissibility,
    CausalEffect,
    Design,
    IdentificationGrade,
    Outcome,
    TransportStatus,
    Treatment,
    support_distance,
    widen,
)
from amtgo.core.uncertainty import UncertainValue
from amtgo.errors import ConfigurationError, ReproducibilityError
from amtgo.scenarios.model import Interval
from amtgo.utils.canonical import content_hash


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DeclaredEffect(_Strict):
    """Effet saisi : I7 (hypothèse d'expert) ou I6 (bornes d'identification partielle)."""

    effect_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    treatment: Treatment
    outcome: Outcome
    source_context: str
    target_context: str
    design: Design
    grade: IdentificationGrade
    bounds: Interval
    time_horizon_years: float = Field(gt=0)
    mechanism: str
    source: str

    @model_validator(mode="after")
    def _declared_grade(self) -> Self:
        if self.grade not in (IdentificationGrade.I6, IdentificationGrade.I7):
            raise ValueError(f"{self.effect_key} : un effet I1–I5 s'estime dans le run, il ne se déclare pas")
        return self

    def to_effect(self) -> CausalEffect:
        transport = (TransportStatus.IDENTIFIED if self.source_context == self.target_context
                     else TransportStatus.UNSUPPORTED)
        return CausalEffect(
            effect_key=self.effect_key, treatment=self.treatment, outcome=self.outcome,
            source_context=self.source_context, target_context=self.target_context, estimand="bounds",
            design=self.design, grade=self.grade, effect=UncertainValue.bounds(self.bounds.lo, self.bounds.hi),
            time_horizon_years=self.time_horizon_years, spillover_model="none", mechanism=self.mechanism,
            transport_status=transport, overlap=1.0 if transport is TransportStatus.IDENTIFIED else 0.0,
            source_ids=(self.source,))


class DiDEstimation(_Strict):
    """Estimation DiD échelonnée sur un panel ingéré dans le run."""

    effect_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    panel_source: str
    outcome_variable: str
    negative_control_variable: str | None = None
    treatment: Treatment
    outcome: Outcome
    source_context: str
    target_context: str
    mechanism: str
    # Modificateurs d'effet comparés source / cible. Seul « density » est calculable à ce stade
    # (population / surface des polygones de ``target_source``) : tout autre est refusé.
    effect_modifiers: tuple[str, ...] = Field(min_length=1)
    target_source: str

    @model_validator(mode="after")
    def _modifiers(self) -> Self:
        unsupported = set(self.effect_modifiers) - {"density"}
        if unsupported:
            raise ValueError(f"{self.effect_key} : modificateurs non calculables {sorted(unsupported)}")
        return self


class TransportRules(_Strict):
    """Recouvrement des modificateurs d'effet entre source et cible (04 §10)."""

    identified_overlap: float = Field(gt=0.0, le=1.0)  # au-delà : IDENTIFIED ; en deçà mais ≥ τ_O : PARTIAL
    partial_widening: float = Field(ge=1.0)  # facteur d'élargissement des bornes en transport PARTIAL


class NoveltyRules(_Strict):
    """U_novel = f(d_A) (04 §14) : élargissement linéaire, puis UNKNOWN au-delà de ``max_distance``."""

    kappa: float = Field(ge=0.0)
    max_distance: float = Field(gt=0.0)


class DiagnosticRules(_Strict):
    alpha: float = Field(gt=0.0, lt=0.5)  # test joint des tendances pré-traitement
    interval_level: float = Field(gt=0.5, lt=1.0)
    bootstrap_draws: int = Field(ge=50, le=2000)
    placebo_shift_years: int = Field(ge=1)


class CausalLibraryManifest(_Strict):
    library_id: str
    version: str
    description: str
    declared: tuple[DeclaredEffect, ...] = ()
    estimations: tuple[DiDEstimation, ...] = ()
    transport: TransportRules
    novelty: NoveltyRules
    diagnostics: DiagnosticRules

    @model_validator(mode="after")
    def _unique(self) -> Self:
        keys = [d.effect_key for d in self.declared] + [e.effect_key for e in self.estimations]
        if len(set(keys)) != len(keys):
            raise ValueError("effect_key dupliqué dans la bibliothèque")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)


@dataclass(frozen=True)
class CausalAnswer:
    """Réponse à une requête : statut, effet (ou rien), et pourquoi."""

    effect_key: str
    status: str  # Admissibility, ou CAUSAL_EFFECT_UNKNOWN
    effect: UncertainValue | None
    grade: IdentificationGrade | None
    reason: str

    @property
    def known(self) -> bool:
        return self.effect is not None

    def interval(self) -> Interval:
        if self.effect is None or self.effect.lower is None or self.effect.upper is None:
            raise ConfigurationError(f"{self.effect_key} : {CAUSAL_EFFECT_UNKNOWN} ({self.reason})")
        return Interval(lo=self.effect.lower, hi=self.effect.upper)

    def draws(self, n: int, rng: np.random.Generator) -> np.ndarray:
        """Tirages pour propager l'incertitude : rééchantillonnage, ou uniforme dans les bornes (déclaré)."""
        if self.effect is not None and self.effect.samples:
            return rng.choice(np.asarray(self.effect.samples), size=n, replace=True)
        return self.interval().sample(rng, n)


class FrozenCausalLibrary:
    """Bibliothèque gelée : lecture seule, empreinte vérifiée."""

    def __init__(self, effects: list[CausalEffect], freeze_hash: str, overlap_min: float,
                 novelty: NoveltyRules) -> None:
        if library_hash(effects) != freeze_hash:
            raise ReproducibilityError("bibliothèque causale altérée après gel")
        self._effects = {e.effect_key: e for e in effects}
        self._hash = freeze_hash
        self._overlap_min = overlap_min
        self._novelty = novelty

    @property
    def freeze_hash(self) -> str:
        return self._hash

    @property
    def keys(self) -> list[str]:
        return sorted(self._effects)

    def record(self, key: str) -> CausalEffect:
        return self._effects[key]  # modèle pydantic gelé : non modifiable

    def query(self, effect_key: str, target_context: str, intensity: float | None = None) -> CausalAnswer:
        e = self._effects.get(effect_key)
        if e is None:
            return CausalAnswer(effect_key, CAUSAL_EFFECT_UNKNOWN, None, None, "aucun enregistrement")
        if e.target_context != target_context:
            return CausalAnswer(effect_key, CAUSAL_EFFECT_UNKNOWN, None, e.grade,
                                f"transport non évalué vers {target_context} (τ_T ≠ τ_S par défaut)")
        adm = e.admissibility(self._overlap_min)
        if adm is Admissibility.UNSUPPORTED:
            why = ("diagnostics échoués" if e.diagnostics_failed else
                   f"transport {e.transport_status.value}, recouvrement {e.overlap:.2f}")
            return CausalAnswer(effect_key, CAUSAL_EFFECT_UNKNOWN, None, e.grade, why)
        effect = e.effect
        reason = f"{e.design.value}, {e.grade.value}, transport {e.transport_status.value}"
        if intensity is not None:
            d = support_distance(intensity, e.treatment.intensity_support)
            if d > self._novelty.max_distance:
                return CausalAnswer(effect_key, CAUSAL_EFFECT_UNKNOWN, None, e.grade,
                                    f"politique hors support (d_A = {d:.2f})")
            if d > 0:
                effect = widen(effect, 1.0 + self._novelty.kappa * d)
                adm = Admissibility.BOUNDED if adm is Admissibility.CAUSAL_FACT else adm
                reason += f", hors support d_A = {d:.2f} : bornes élargies"
        return CausalAnswer(effect_key, adm.value, effect, e.grade, reason)


def library_hash(effects: list[CausalEffect]) -> str:
    return content_hash(sorted((e.effect_key, e.content_hash) for e in effects))


def effect_to_json(e: CausalEffect) -> dict[str, Any]:
    return {"effect_id": e.effect_id, **e.model_dump(mode="json")}


def effect_from_json(d: dict[str, Any]) -> CausalEffect:
    d = dict(d)
    d.pop("effect_id", None)
    return CausalEffect.model_validate(d)


def interval_summary(u: UncertainValue | None) -> dict[str, float | None] | None:
    return None if u is None else {"mean": u.mean, "lower": u.lower, "upper": u.upper}

