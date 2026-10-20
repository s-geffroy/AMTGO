"""RunRequest et RunManifest (prompt §52, 07 §18, 07 §21).

Une *requête* de run référence des fichiers de configuration. À la soumission,
elle est *résolue* : chaque référence est chargée, validée et remplacée par son
contenu et son empreinte. Le RunManifest qui en résulte est autosuffisant et
gelé : modifier un fichier de configuration après coup ne change pas un run
déjà soumis, il en crée un nouveau.

Il n'existe pas de run « neutre » : régime constitutionnel et manifeste
normatif sont obligatoires (07 §21).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from amtgo.config.loader import load_model
from amtgo.core.enums import MapMode
from amtgo.core.provenance import utcnow
from amtgo.data.sources import SourceManifest
from amtgo.errors import ConfigurationError
from amtgo.geo.mesh import MeshDefinition
from amtgo.institutions.regimes import ConstitutionalRegime, load_regime
from amtgo.manifests.normative import NormativeManifest
from amtgo.utils.canonical import content_hash, stable_uuid
from amtgo.utils.code_version import code_commit, code_version

# Rôle requis pour qu'une source serve d'emprise à un maillage.
ROLE_ANALYSIS_EXTENT = "analysis_extent"


class SourceUse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest: str  # chemin relatif à configs/
    roles: tuple[str, ...] = Field(min_length=1)  # chaque usage est vérifié là où il a lieu
    redistribute: bool = False


class RunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    description: str
    region: str
    map_mode: MapMode = MapMode.R
    constitutional_regime: str
    normative_manifest: str
    sources: tuple[SourceUse, ...]
    mesh_set: tuple[str, ...]
    ontology_set: tuple[str, ...] = ()
    scenario_set: tuple[str, ...] = ()
    seeds: tuple[int, ...] = (0,)


class ResolvedSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    use: SourceUse
    manifest: SourceManifest
    manifest_hash: str


class RunManifest(BaseModel):
    """Manifeste gelé. ``run_id`` dérive du contenu (hors ``created_at``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: uuid.UUID
    manifest_hash: str
    created_at: datetime
    code_commit: str
    code_version: str
    request: RunRequest
    data_manifest: tuple[ResolvedSource, ...]
    normative_manifest: NormativeManifest
    normative_manifest_hash: str
    constitutional_regime: ConstitutionalRegime
    constitutional_regime_hash: str
    mesh_set: tuple[MeshDefinition, ...]
    # Couches non encore disponibles : explicitement nulles, jamais inventées.
    measurement_model: dict[str, Any] | None = None
    ontology_set: tuple[str, ...] = ()
    causal_library: dict[str, Any] | None = None
    scenario_set: tuple[str, ...] = ()
    solver: dict[str, Any] | None = None
    seeds: tuple[int, ...]

    @property
    def data_manifest_hash(self) -> str:
        return content_hash([s.manifest_hash for s in self.data_manifest])


_UNHASHED = {"run_id", "manifest_hash", "created_at"}


def manifest_body_hash(manifest: RunManifest) -> str:
    """Empreinte de tout le contenu, hors identité et horodatage."""
    return content_hash(manifest.model_dump(mode="json", exclude=_UNHASHED))


def resolve_request(request: RunRequest, configs_dir: Path) -> RunManifest:
    if request.map_mode is MapMode.C_DEEP:
        raise ConfigurationError("Map-C-Deep : branche de recherche séparée, non implémentée (prompt §77)")
    if request.ontology_set or request.scenario_set:
        raise ConfigurationError("ontologies (M4) et scénarios (M6) pas encore disponibles")
    if not request.mesh_set:
        raise ConfigurationError("au moins un maillage est requis")

    sources = []
    seen: set[str] = set()
    for use in request.sources:
        m = load_model(SourceManifest, configs_dir / use.manifest)
        if m.source_id in seen:
            raise ConfigurationError(f"source dupliquée : {m.source_id}")
        seen.add(m.source_id)
        for role in use.roles:
            m.require_role(role)
        sources.append(ResolvedSource(use=use, manifest=m, manifest_hash=m.content_hash))

    normative = load_model(NormativeManifest, configs_dir / request.normative_manifest)
    regime = load_regime(configs_dir, request.constitutional_regime)
    meshes = tuple(load_model(MeshDefinition, configs_dir / p) for p in request.mesh_set)
    ids = [m.mesh_id for m in meshes]
    if len(set(ids)) != len(ids):
        raise ConfigurationError(f"mesh_id dupliqué dans mesh_set : {ids}")
    for mesh in meshes:
        if mesh.extent.kind == "source_union":
            use_for = next((s for s in sources if s.manifest.source_id == mesh.extent.source_id), None)
            if use_for is None:
                raise ConfigurationError(f"{mesh.mesh_id} : emprise sur une source absente du run")
            if ROLE_ANALYSIS_EXTENT not in use_for.use.roles:
                raise ConfigurationError(
                    f"{mesh.mesh_id} : la source {mesh.extent.source_id} n'est pas déclarée "
                    f"pour le rôle {ROLE_ANALYSIS_EXTENT!r} dans ce run")

    body: dict[str, Any] = {
        "code_commit": code_commit(),
        "code_version": code_version(),
        "request": request,
        "data_manifest": tuple(sources),
        "normative_manifest": normative,
        "normative_manifest_hash": normative.content_hash,
        "constitutional_regime": regime,
        "constitutional_regime_hash": regime.content_hash,
        "mesh_set": meshes,
        "seeds": request.seeds,
    }
    draft = RunManifest(run_id=uuid.UUID(int=0), manifest_hash="", created_at=utcnow(), **body)
    h = manifest_body_hash(draft)
    return draft.model_copy(update={"run_id": stable_uuid("run", h), "manifest_hash": h})


def verify_manifest(manifest: RunManifest) -> None:
    """Recalcule l'empreinte : un manifeste modifié après soumission est détecté."""
    from amtgo.errors import ReproducibilityError

    if manifest_body_hash(manifest) != manifest.manifest_hash:
        raise ReproducibilityError(f"run {manifest.run_id} : manifeste altéré")
