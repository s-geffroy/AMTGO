"""Contrat d'ingestion (prompt §67).

Le réseau n'est touché que dans ``fetch``. Le cœur analytique ne voit que des
observations normalisées.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Protocol

from amtgo.data.observations import Observation
from amtgo.data.sources import ResourceRef, SourceManifest


class SourceAdapter(Protocol):
    def discover(self, manifest: SourceManifest) -> list[ResourceRef]:
        """Ressources à récupérer pour cette source (sans réseau)."""
        ...

    def fetch(self, manifest: SourceManifest, ref: ResourceRef, cache_dir: Path) -> Path:
        """Récupère ``ref`` dans ``cache_dir`` et renvoie le chemin local."""
        ...

    def validate(self, manifest: SourceManifest, ref: ResourceRef, path: Path) -> str:
        """Vérifie l'intégrité (checksum) et renvoie l'empreinte ``sha256:<hex>``."""
        ...

    def normalize(
        self, manifest: SourceManifest, files: dict[str, Path], recorded_at: datetime
    ) -> Iterator[Observation]:
        """Transforme les fichiers validés en observations typées."""
        ...
