"""Récupération de fichiers épinglés (http ou local) avec vérification sha256."""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

from amtgo.data.sources import ResourceRef, RetrievalKind, SourceManifest
from amtgo.errors import ConfigurationError, ProvenanceError
from amtgo.utils.canonical import file_sha256

# Délai réseau d'une récupération : borne technique, pas paramètre scientifique.
HTTP_TIMEOUT_S = 60


class PinnedFileMixin:
    """discover/fetch/validate communs aux sources fondées sur des fichiers épinglés."""

    def discover(self, manifest: SourceManifest) -> list[ResourceRef]:
        return list(manifest.retrieval.resources)

    def fetch(self, manifest: SourceManifest, ref: ResourceRef, cache_dir: Path) -> Path:
        if not ref.sha256:
            raise ConfigurationError(f"{ref.name} : sha256 manquant")
        target = cache_dir / manifest.source_id / manifest.release / ref.name
        if target.exists() and file_sha256(target) == _norm(ref.sha256):
            return target  # cache adressé par contenu : rien à refaire
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        kind = manifest.retrieval.kind
        if kind is RetrievalKind.HTTP:
            assert ref.url is not None
            with urllib.request.urlopen(ref.url, timeout=HTTP_TIMEOUT_S) as resp, tmp.open("wb") as fh:
                shutil.copyfileobj(resp, fh)
        elif kind is RetrievalKind.LOCAL:
            assert ref.path is not None
            shutil.copyfile(Path(ref.path), tmp)
        else:
            raise ConfigurationError(f"{manifest.source_id} : retrieval {kind.value} sans fichier")
        tmp.replace(target)
        return target

    def validate(self, manifest: SourceManifest, ref: ResourceRef, path: Path) -> str:
        actual = file_sha256(path)
        expected = _norm(ref.sha256 or "")
        if actual != expected:
            raise ProvenanceError(
                f"{manifest.source_id}/{ref.name} : checksum {actual} ≠ attendu {expected}"
            )
        return actual


def _norm(sha: str) -> str:
    return sha if sha.startswith("sha256:") else "sha256:" + sha
