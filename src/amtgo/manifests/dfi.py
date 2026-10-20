"""DFIManifest : paramètres de modèle de l'évaluation D/F/I (M5), figés dans le RunManifest."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.core.channels import IntegChannel
from amtgo.utils.canonical import content_hash


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReificationSpec(_Strict):
    """Effet de l'institutionnalisation sur la saillance : clé de la bibliothèque causale gelée (M7)."""

    effect: str
    horizon_years: float = Field(gt=0)


class DFIManifest(_Strict):
    model_id: str
    version: str
    description: str
    network_kernel_length_km: float = Field(gt=0)
    network_kernel_cutoff: float = Field(gt=1)  # en multiples de la longueur
    # Qualité des contacts par canal d'intégration : DÉCLARÉE (hypothèse) faute de mesure.
    integration_quality: dict[IntegChannel, float]
    status_quo: str  # chemin relatif à configs/
    reification: ReificationSpec | None = None
    # Plancher numérique des écarts relatifs (S^ontology, S^scale sur D/F/I).
    relative_floor: float = Field(gt=0)

    @model_validator(mode="after")
    def _unit(self) -> Self:
        for c, q in self.integration_quality.items():
            if not 0.0 <= q <= 1.0:
                raise ValueError(f"qualité {c} hors [0,1]")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)
