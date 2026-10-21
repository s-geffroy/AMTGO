"""Manifeste de la branche de recherche Map-C-Deep (02 §22, 04 §20-21, 11 phase 11).

Séparée du produit principal : une requête ``kind: c_deep`` n'est pas un RunRequest,
ne porte ni sources contemporaines ni bibliothèque causale (aucun coefficient
contemporain n'est extrapolé sur 150 ans), et son produit n'entre dans aucune archive.

Seul un monde historique **synthétique** est admis : aucun adaptateur de données
historiques réelles n'existe, et un SCM historique non validé sur vérité connue ne
peut pas être appliqué à une histoire réelle. Le contre-factuel ne change que des
frontières et des capitales : jamais de déplacement de population.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.config.loader import load_model
from amtgo.core.provenance import utcnow
from amtgo.research.historical_scm import PARAMS, STEP_YEARS, Model
from amtgo.utils.canonical import content_hash, stable_uuid
from amtgo.utils.code_version import code_commit, code_version

KIND: Literal["c_deep"] = "c_deep"
STATUS = "HISTORICAL_COUNTERFACTUAL — NON_PRESCRIPTIVE"


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Town(_Strict):
    x: float
    y: float
    peak: float = Field(gt=0)
    scale_km: float = Field(gt=0)


class GroupField(_Strict):
    """Part du second groupe fictif : un noyau gaussien (vérité du monde synthétique)."""

    x: float
    y: float
    scale_km: float = Field(gt=0)
    max_share: float = Field(gt=0, lt=1)


class Kernels(_Strict):
    migration_km: float = Field(gt=0)
    capital_km: float = Field(gt=0)
    ties_km: float = Field(gt=0)


class SyntheticHistoricalWorld(_Strict):
    seed: int
    nx: int = Field(ge=4, le=40)
    ny: int = Field(ge=4, le=40)
    spacing_km: float = Field(gt=0)
    background: float = Field(gt=0)
    towns: tuple[Town, ...]
    groups: tuple[str, str]
    second_group: GroupField
    identity_initial: float = Field(ge=0, le=1)
    growth_per_decade: float = Field(ge=-0.5, le=1.0)
    kernels: Kernels
    truth: dict[str, float]  # θ vrai : sert à générer l'histoire et à calibrer, jamais à estimer

    @model_validator(mode="after")
    def _truth(self) -> Self:
        if set(self.truth) != set(PARAMS):
            raise ValueError(f"truth : exactement {list(PARAMS)}")
        return self


class InstitutionalEpoch(_Strict):
    """Institutions en vigueur à partir de ``year`` : une ligne de partition (ou aucune), des capitales."""

    year: int
    border_x: float | None = None  # cellules x ≥ border_x : seconde entité
    capitals: tuple[tuple[int, int], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _capitals(self) -> Self:
        if len(self.capitals) != (1 if self.border_x is None else 2):
            raise ValueError("une capitale par entité politique")
        return self


class HistorySpec(_Strict):
    start: int
    end: int
    factual: tuple[InstitutionalEpoch, ...] = Field(min_length=1)
    counterfactual: tuple[InstitutionalEpoch, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _grid(self) -> Self:
        if (self.end - self.start) % STEP_YEARS:
            raise ValueError(f"l'horizon doit être un multiple de {STEP_YEARS} ans")
        for name, epochs in (("factual", self.factual), ("counterfactual", self.counterfactual)):
            if epochs[0].year != self.start or any((e.year - self.start) % STEP_YEARS for e in epochs):
                raise ValueError(f"{name} : époques alignées sur la grille décennale, la première au départ")
        return self


class ObservationDesign(_Strict):
    census_years: tuple[int, ...] = Field(min_length=1)
    share_years: tuple[int, ...]
    survey_years: tuple[int, ...]
    block: tuple[int, int]
    noise: dict[str, float]

    @model_validator(mode="after")
    def _noise(self) -> Self:
        if set(self.noise) != {"census", "init", "shares", "survey"} or any(v <= 0 for v in self.noise.values()):
            raise ValueError("noise : census, init, shares, survey, strictement positifs")
        return self


class Placebo(_Strict):
    border_y: float  # ligne fictive où aucune frontière n'a jamais existé
    year: int


class ValidationSpec(_Strict):
    holdout_from: int  # recensements et enquêtes à partir de cette année : hors échantillon
    # Moyenne quadratique des résidus hors échantillon, en unités du bruit déclaré (≈ 1 sous un modèle correct).
    tolerance_rms_z: float = Field(gt=0)
    placebo: Placebo
    placebo_z: float = Field(gt=0)  # |β_placebo| ≤ z·se
    bootstrap: int = Field(ge=5, le=200)
    seed: int
    interval_level: float = Field(gt=0.5, lt=1.0)
    # Une validation factuelle ne valide pas un contre-factuel : une forme structurelle fausse passe le
    # Gate H et manque la vérité contre-factuelle (red-team). L'ensemble doit en garder au moins deux.
    min_structural_forms: int = Field(default=2, ge=2)


class CDeepRequest(_Strict):
    kind: Literal["c_deep"]
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    description: str
    world: SyntheticHistoricalWorld
    history: HistorySpec
    observation: ObservationDesign
    models: tuple[Model, ...] = Field(min_length=2)
    validation: ValidationSpec
    reference_line_x: float  # ligne autour de laquelle les indicateurs sont lus (frontière factuelle)


class CDeepManifest(_Strict):
    kind: Literal["c_deep"] = KIND
    run_id: uuid.UUID
    manifest_hash: str
    created_at: datetime
    code_commit: str
    code_version: str
    status: str = STATUS
    request: CDeepRequest


_UNHASHED = {"run_id", "manifest_hash", "created_at"}


def body_hash(m: CDeepManifest) -> str:
    return content_hash(m.model_dump(mode="json", exclude=_UNHASHED))


def resolve_c_deep(path: Path) -> CDeepManifest:
    request = load_model(CDeepRequest, path)
    draft = CDeepManifest(run_id=uuid.UUID(int=0), manifest_hash="", created_at=utcnow(), code_commit=code_commit(),
                          code_version=code_version(), request=request)
    h = body_hash(draft)
    return draft.model_copy(update={"run_id": stable_uuid("c_deep", h), "manifest_hash": h})


def verify_c_deep(m: CDeepManifest) -> None:
    from amtgo.errors import ReproducibilityError

    if body_hash(m) != m.manifest_hash:
        raise ReproducibilityError(f"run Map-C-Deep {m.run_id} : manifeste altéré")
