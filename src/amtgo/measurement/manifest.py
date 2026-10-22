"""MeasurementManifest : modèle de mesure déclaré, versionné, figé dans le RunManifest.

Ses paramètres sont des paramètres de *modèle* (prior, inflation de variance,
seuils de calculabilité), distincts des paramètres *normatifs*. Ils restent
explicites pour que leur sensibilité puisse être rapportée.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.utils.canonical import content_hash


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LikelihoodModel(StrEnum):
    EA_COUNT_DENSITY = "ea_count_density"  # compte d'une zone d'énumération de surface connue
    AREA_TOTAL = "area_total"  # total d'un polygone administratif


class Period(_Strict):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.start > self.end:
            raise ValueError("période : start > end")
        return self


class GaussianDensityPrior(_Strict):
    """Densité indépendante par cellule : Z_i = ρ_i A_i, ρ_i ~ N(m, s²).

    Référence linéaire exacte (tests). Inadaptée aux priors peu informatifs : une
    loi normale de CV élevé met une masse importante sous zéro.
    """

    kind: Literal["independent_density"]
    density_mean_per_km2: float = Field(ge=0)
    density_sd_per_km2: float = Field(gt=0)


class LogNormalDensityPrior(_Strict):
    """log ρ_i ~ N(log médiane, σ²) : peu informatif ET positif par construction."""

    kind: Literal["independent_lognormal_density"]
    median_density_per_km2: float = Field(gt=0)
    log_sd: float = Field(gt=0)


class RasterLogNormalDensityPrior(_Strict):
    """log ρ_i ~ N(log ρ̂_i, σ²), ρ̂_i lue sur un raster de population (WorldPop) agrégé à la cellule.

    Le raster est un produit modélisé (statut M) : il sert de *prior*, jamais
    d'observation (03 §5). Une cellule où le raster ne place personne reçoit le
    plancher, pas zéro : le prior reste positif et l'absence d'habitat détecté
    n'est pas une absence prouvée.
    """

    kind: Literal["raster_lognormal_density"]
    source_id: str
    variable_id: str
    log_sd: float = Field(gt=0)
    floor_density_per_km2: float = Field(gt=0)
    # Pixels agrégés par bloc avant l'affectation aux cellules (lecture par bandes, mémoire bornée).
    block_pixels: int = Field(ge=1, le=100)


PriorSpec = GaussianDensityPrior | LogNormalDensityPrior | RasterLogNormalDensityPrior


class ObservationUse(StrEnum):
    LIKELIHOOD = "likelihood"  # entre dans l'ajustement de la structure relative
    MARGIN = "margin"  # total administratif : recalage exact des tirages (désagrégation)


class LikelihoodSpec(_Strict):
    source_id: str
    variable_id: str
    model: LikelihoodModel
    use: ObservationUse = ObservationUse.LIKELIHOOD
    # Inflation explicite de la variance d'observation (≥ 1) : paramètre de modèle.
    variance_inflation: float = Field(default=1.0, ge=1.0)
    # Erreur de représentativité (CV) : une mesure ponctuelle d'un champ hétérogène ne
    # vaut pas la densité moyenne de la cellule. r += (cv · y)². Paramètre de modèle.
    representativeness_cv: float = Field(default=0.0, ge=0.0)


class QualityGates(_Strict):
    """Exclusion d'observations sur dimensions de qualité, une à une (pas de score agrégé)."""

    min_construct_validity: float = Field(ge=0, le=1)
    min_privacy_usability: float = Field(ge=0, le=1)
    min_license_usability: float = Field(ge=0, le=1)


class SamplingSpec(_Strict):
    n_samples: int = Field(ge=20)
    seed: int
    interval_level: float = Field(gt=0, lt=1)


class ValidationSpec(_Strict):
    holdout_fraction: float = Field(gt=0, lt=1)


class ComputabilitySpec(_Strict):
    a_min: float = Field(ge=0, le=1)
    b_min: float = Field(ge=0, le=1)
    c_min: float = Field(ge=0, le=1)
    max_negative_sample_fraction: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.a_min >= self.b_min >= self.c_min:
            raise ValueError("seuils de calculabilité : a_min ≥ b_min ≥ c_min attendu")
        return self


class MeasurementManifest(_Strict):
    model_id: str
    version: str
    variable_id: str
    description: str
    target_period: Period
    prior: PriorSpec = Field(discriminator="kind")
    likelihoods: tuple[LikelihoodSpec, ...] = Field(min_length=1)
    quality_gates: QualityGates
    sampling: SamplingSpec
    validation: ValidationSpec
    computability: ComputabilitySpec

    @model_validator(mode="after")
    def _unique_sources(self) -> Self:
        ids = [lk.source_id for lk in self.likelihoods]
        if len(set(ids)) != len(ids):
            raise ValueError("une seule vraisemblance par source")
        for lk in self.likelihoods:
            if lk.use is ObservationUse.MARGIN:
                if lk.model is not LikelihoodModel.AREA_TOTAL:
                    raise ValueError(f"{lk.source_id} : seule une vraisemblance area_total peut servir de marge")
                if not isinstance(self.prior, LogNormalDensityPrior | RasterLogNormalDensityPrior):
                    raise ValueError("les marges exigent un prior positif (log-normal)")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)
