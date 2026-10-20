"""Hyperarêtes et infrastructures (prompt §26-27, 02 §4, 02 §16).

Une hyperarête relie plusieurs territoires à la fois (fleuve, corridor pastoral,
métropole…). Comme **overlay institutionnel**, elle atténue la charge
frontalière de certains canaux entre ses membres : μ^g_ijc ∈ [0,1] (02 §10).
Aucune hyperarête, culturelle ou autre, ne donne automatiquement une
souveraineté : elle porte des compétences, pas un statut.

Infrastructure observée et potentielle sont stockées séparément : la cohérence
fonctionnelle ne récompense pas un réseau historiquement inégal parce qu'il
existe déjà (prompt §26).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.core.channels import FragChannel, IntegChannel


class HyperedgeType(StrEnum):
    """Union des listes du prompt §27 et de 02 §4 (ADR-0003)."""

    RIVER = "river"
    LAKE = "lake"
    CORRIDOR = "corridor"
    PASTORAL = "pastoral"
    METRO = "metro"
    CULTURAL = "cultural"
    INDUSTRIAL = "industrial"
    ENERGY = "energy"
    TRADE = "trade"
    SECURITY = "security"
    HISTORICAL = "historical"


class Hyperedge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hyperedge_id: str
    type: HyperedgeType
    members: tuple[str, ...] = Field(min_length=2)  # identifiants de cellules
    groups: tuple[str, ...] | None = None  # None : tous les groupes
    mitigation: dict[FragChannel | IntegChannel, float]  # μ par canal

    @model_validator(mode="after")
    def _unit(self) -> Self:
        for c, m in self.mitigation.items():
            if not 0.0 <= m <= 1.0:
                raise ValueError(f"{self.hyperedge_id} : μ {c} hors [0,1]")
        return self

    def member_mask(self, cell_ids: list[str]) -> np.ndarray:
        members = set(self.members)
        return np.array([c in members for c in cell_ids])


class InfrastructureLink(BaseModel):
    """Connectivité d'une paire de cellules : K_obs (observée) et K_pot (potentielle) séparés."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: str
    destination: str
    k_observed: float = Field(ge=0)
    k_potential: float = Field(ge=0)

    @property
    def deficit(self) -> float:
        """Sous-investissement : potentiel non réalisé (jamais une « preuve » d'inutilité)."""
        return max(0.0, self.k_potential - self.k_observed)
