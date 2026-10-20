"""Registre de sources (M1) : SourceManifest déclaratif et entité Source persistée.

Un manifeste (prompt §69, schéma 10 §1) dit ce qu'est une source, sous quelle
licence, dans quelle zone de données, et surtout à quoi elle peut servir et à
quoi elle ne doit **jamais** servir (rôles autorisés / interdits, 03).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.config.loader import load_model
from amtgo.core.entity import Entity
from amtgo.core.enums import DataZone, EvidenceStatus, PrivacyClass
from amtgo.core.quality import QualityVector
from amtgo.data.licenses import License
from amtgo.errors import DataLicenseError, ForbiddenSourceRole
from amtgo.utils.canonical import content_hash, stable_uuid


class AccessLevel(StrEnum):
    OPEN = "open"
    RESTRICTED = "restricted"
    SENSITIVE = "sensitive"


class RetrievalKind(StrEnum):
    HTTP = "http"  # URL épinglée + sha256
    LOCAL = "local"  # fichier déposé localement (données restreintes : jamais dans le dépôt)
    SYNTHETIC = "synthetic"  # généré de façon déterministe par un adapter


class ResourceRef(BaseModel):
    """Un fichier d'une source. ``sha256`` obligatoire hors synthétique : pas d'ingestion non épinglée."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    url: str | None = None
    path: str | None = None
    sha256: str | None = None


class Retrieval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: RetrievalKind
    adapter: str  # nom enregistré dans amtgo.data.adapters.ADAPTERS
    resources: tuple[ResourceRef, ...] = ()
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _pinned(self) -> Self:
        if self.kind is RetrievalKind.SYNTHETIC:
            return self
        if not self.resources:
            raise ValueError("au moins une ressource est requise")
        for r in self.resources:
            if not r.sha256:
                raise ValueError(f"ressource {r.name!r} sans sha256 : ingestion non reproductible")
            if self.kind is RetrievalKind.HTTP and not r.url:
                raise ValueError(f"ressource {r.name!r} : url requise pour kind=http")
            if self.kind is RetrievalKind.LOCAL and not r.path:
                raise ValueError(f"ressource {r.name!r} : path requis pour kind=local")
        return self


class SourceRoles(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: tuple[str, ...]
    forbidden: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _disjoint(self) -> Self:
        both = set(self.allowed) & set(self.forbidden)
        if both:
            raise ValueError(f"rôles à la fois autorisés et interdits : {sorted(both)}")
        return self


class HistoricalContext(BaseModel):
    """Obligatoire pour une source historique (01 §29) : la carte ancienne est un instrument."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    author: str
    purpose: str
    method: str
    colonial_context: str
    ontology: str


class SourceManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    name: str
    provider: str
    release: str
    url: str | None = None
    citation: str
    license: License
    access: AccessLevel
    data_zone: DataZone
    privacy_class: PrivacyClass
    roles: SourceRoles
    method: str
    temporal_start: date | None = None
    temporal_end: date | None = None
    temporal_note: str | None = None
    default_evidence_status: EvidenceStatus
    quality: QualityVector
    retrieval: Retrieval
    historical_context: HistoricalContext | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _coherence(self) -> Self:
        if self.temporal_start and self.temporal_end and self.temporal_start > self.temporal_end:
            raise ValueError("temporal_start > temporal_end")
        if self.data_zone in (DataZone.OPEN_CORE, DataZone.DERIVED_EXPORTABLE):
            if not self.license.redistribution:
                raise ValueError(f"{self.data_zone.value} exige une licence redistribuable")
            if self.access is not AccessLevel.OPEN:
                raise ValueError(f"{self.data_zone.value} exige access=open")
        if self.data_zone is DataZone.SENSITIVE and self.privacy_class.rank < PrivacyClass.SENSITIVE.rank:
            raise ValueError("zone SENSITIVE : privacy_class doit être SENSITIVE ou PROHIBITED")
        if self.access is AccessLevel.SENSITIVE and self.data_zone is not DataZone.SENSITIVE:
            raise ValueError("access=sensitive impose data_zone=SENSITIVE")
        if self.data_zone is not DataZone.OPEN_CORE and self.retrieval.kind is RetrievalKind.HTTP:
            # Une source restreinte n'est jamais téléchargée vers un chemin du dépôt ; elle est
            # déposée localement par une personne autorisée (prompt §68).
            raise ValueError("seules les sources OPEN_CORE peuvent être récupérées par http")
        if self.default_evidence_status is EvidenceStatus.HISTORICAL and not self.historical_context:
            raise ValueError("source historique sans historical_context (01 §29)")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)

    @property
    def source_uuid(self) -> uuid.UUID:
        return stable_uuid("source", {"source_id": self.source_id, "release": self.release})

    def require_role(self, role: str) -> None:
        """Lève si ``role`` est interdit ou non déclaré pour cette source."""
        if role in self.roles.forbidden:
            raise ForbiddenSourceRole(f"{self.source_id} : rôle {role!r} explicitement interdit")
        if role not in self.roles.allowed:
            raise ForbiddenSourceRole(f"{self.source_id} : rôle {role!r} non autorisé")

    def require_license(self, *, redistribute: bool, commercial: bool) -> None:
        if redistribute and not self.license.redistribution:
            raise DataLicenseError(f"{self.source_id} : redistribution interdite par {self.license.license_id}")
        if commercial and not self.license.commercial_use:
            raise DataLicenseError(f"{self.source_id} : usage commercial interdit par {self.license.license_id}")


def load_source_manifest(path: Path) -> SourceManifest:
    return load_model(SourceManifest, path)


class Source(Entity):
    """Source effectivement ingérée : le manifeste plus l'empreinte des fichiers récupérés."""

    slug: str
    release: str
    manifest_hash: str
    retrieved_at: datetime
    checksum: str
    privacy_class: PrivacyClass
    data_zone: DataZone
    license_id: str

    @classmethod
    def from_manifest(cls, manifest: SourceManifest, retrieved_at: datetime, checksum: str) -> Source:
        return cls(
            id=manifest.source_uuid,
            version=manifest.release,
            slug=manifest.source_id,
            release=manifest.release,
            manifest_hash=manifest.content_hash,
            retrieved_at=retrieved_at,
            checksum=checksum,
            privacy_class=manifest.privacy_class,
            data_zone=manifest.data_zone,
            license_id=manifest.license.license_id,
        )
