"""Modèle de licence (prompt §68, M1).

Toute ingestion vérifie licence, redistribution, usage commercial et privacy.
La licence décrit ce que *la source* permet ; l'usage prévu est déclaré par le
manifeste de source, et l'incompatibilité est une erreur, pas un avertissement.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class License(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    license_id: str  # identifiant SPDX quand il existe (CC-BY-4.0, ODbL-1.0…) ou libellé stable
    name: str
    url: str | None = None
    redistribution: bool
    commercial_use: bool
    attribution_required: bool
    share_alike: bool = False
    notes: str | None = None
