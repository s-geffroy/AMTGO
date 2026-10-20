"""Base commune des entités persistables (prompt §9).

Toute entité a : un identifiant stable, une version, une provenance, des
horodatages et une validation. La validation structurelle est celle de
pydantic ; la validation sémantique (invariants métier) passe par
:meth:`Entity.check`, appelée à la construction.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.core.provenance import utcnow


class EntityProvenance(BaseModel):
    """Références de lignée : sources et transformations dont l'entité dérive."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ids: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()
    note: str | None = None


class Entity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)

    id: uuid.UUID
    version: str = "1"
    provenance: EntityProvenance = Field(default_factory=EntityProvenance)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _semantic(self) -> Self:
        if self.updated_at is not None and self.updated_at < self.created_at:
            raise ValueError("updated_at antérieur à created_at")
        self.check()
        return self

    def check(self) -> None:
        """Invariants métier. À surcharger ; lever ValueError ou une AMTGOError."""
