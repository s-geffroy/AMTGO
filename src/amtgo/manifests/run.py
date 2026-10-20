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
from amtgo.institutions.status_quo import StatusQuoSpec
from amtgo.manifests.dfi import DFIManifest
from amtgo.manifests.normative import NormativeManifest
from amtgo.measurement.composition import CompositionManifest
from amtgo.measurement.manifest import MeasurementManifest
from amtgo.ontology.model import Ontology, OntologyCrosswalk
from amtgo.utils.canonical import content_hash, stable_uuid
from amtgo.utils.code_version import code_commit, code_version

# Rôle requis pour qu'une source serve d'emprise à un maillage.
ROLE_ANALYSIS_EXTENT = "analysis_extent"
# Rôle requis pour qu'une source fournisse les polygones du statu quo institutionnel.
ROLE_STATUS_QUO = "status_quo_geometry"


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
    measurement_model: str | None = None
    composition_model: str | None = None
    dfi_model: str | None = None
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
    measurement_model: MeasurementManifest | None = None
    ontology_set: tuple[Ontology, ...] = ()
    composition_model: CompositionManifest | None = None
    crosswalks: tuple[OntologyCrosswalk, ...] = ()
    dfi_model: DFIManifest | None = None
    status_quo: StatusQuoSpec | None = None
    # Couches non encore disponibles : explicitement nulles, jamais inventées.
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
    if request.scenario_set:
        raise ConfigurationError("scénarios (M6) pas encore disponibles")
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

    measurement = None
    if request.measurement_model:
        measurement = load_model(MeasurementManifest, configs_dir / request.measurement_model)
        _check_measurement(measurement, sources)

    ontologies = tuple(load_model(Ontology, configs_dir / p) for p in request.ontology_set)
    if len({o.ontology_id for o in ontologies}) != len(ontologies):
        raise ConfigurationError("ontologie dupliquée dans ontology_set")
    composition = None
    crosswalks: tuple[OntologyCrosswalk, ...] = ()
    if request.composition_model:
        if measurement is None:
            raise ConfigurationError("la composition exige un modèle de mesure de population (M3)")
        composition = load_model(CompositionManifest, configs_dir / request.composition_model)
        crosswalks = _check_composition(composition, ontologies, sources, configs_dir)

    dfi = status_quo = None
    if request.dfi_model:
        if composition is None:
            raise ConfigurationError("D/F/I exige la composition (M4) et la population (M3) du run")
        dfi = load_model(DFIManifest, configs_dir / request.dfi_model)
        status_quo = load_model(StatusQuoSpec, configs_dir / dfi.status_quo)
        by_id = {s.manifest.source_id: s for s in sources}
        for lv in status_quo.levels:
            if lv.from_source is not None and (
                    lv.from_source not in by_id or ROLE_STATUS_QUO not in by_id[lv.from_source].use.roles):
                raise ConfigurationError(
                    f"statu quo : la source {lv.from_source} doit être déclarée avec le rôle {ROLE_STATUS_QUO!r}")

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
        "measurement_model": measurement,
        "ontology_set": ontologies,
        "composition_model": composition,
        "crosswalks": crosswalks,
        "dfi_model": dfi,
        "status_quo": status_quo,
        "seeds": request.seeds,
    }
    draft = RunManifest(run_id=uuid.UUID(int=0), manifest_hash="", created_at=utcnow(), **body)
    h = manifest_body_hash(draft)
    return draft.model_copy(update={"run_id": stable_uuid("run", h), "manifest_hash": h})


def _check_measurement(m: MeasurementManifest, sources: list[ResolvedSource]) -> None:
    from amtgo.data.sources import RetrievalKind
    from amtgo.measurement.engine import ROLE_MEASUREMENT

    by_id = {s.manifest.source_id: s for s in sources}
    for lk in m.likelihoods:
        s = by_id.get(lk.source_id)
        if s is None:
            raise ConfigurationError(f"mesure : la source {lk.source_id} n'est pas dans le run")
        if ROLE_MEASUREMENT not in s.use.roles:
            raise ConfigurationError(f"mesure : rôle {ROLE_MEASUREMENT!r} non déclaré pour {lk.source_id}")
    synthetic = [s.manifest for s in sources if s.manifest.retrieval.kind is RetrievalKind.SYNTHETIC]
    if synthetic:
        from amtgo.data.adapters.synthetic import world_of

        if len({world_of(sm).world_hash for sm in synthetic}) > 1:
            raise ConfigurationError("sources synthétiques issues de mondes différents dans un même run")


def _check_composition(m: CompositionManifest, ontologies: tuple[Ontology, ...],
                       sources: list[ResolvedSource], configs_dir: Path) -> tuple[OntologyCrosswalk, ...]:
    from amtgo.measurement.composition import ROLE_COMPOSITION, ROLE_ONTOLOGY_VALIDATION

    by_id = {o.ontology_id: o for o in ontologies}
    if m.observed_ontology not in by_id:
        raise ConfigurationError(f"composition : ontologie observée {m.observed_ontology} absente d'ontology_set")
    src = {s.manifest.source_id: s for s in sources}
    if m.source_id not in src or ROLE_COMPOSITION not in src[m.source_id].use.roles:
        raise ConfigurationError(f"composition : rôle {ROLE_COMPOSITION!r} non déclaré pour {m.source_id}")
    for vs in m.validation_sources:
        if vs.source_id not in src or ROLE_ONTOLOGY_VALIDATION not in src[vs.source_id].use.roles:
            raise ConfigurationError(f"composition : rôle {ROLE_ONTOLOGY_VALIDATION!r} non déclaré pour {vs.source_id}")
    crosswalks = []
    for proj in m.projections:
        if proj.ontology not in by_id:
            raise ConfigurationError(f"composition : ontologie cible {proj.ontology} absente d'ontology_set")
        cw = load_model(OntologyCrosswalk, configs_dir / proj.crosswalk)
        cw.check_against(by_id[m.observed_ontology], by_id[proj.ontology])
        crosswalks.append(cw)
    return tuple(crosswalks)


def verify_manifest(manifest: RunManifest) -> None:
    """Recalcule l'empreinte : un manifeste modifié après soumission est détecté."""
    from amtgo.errors import ReproducibilityError

    if manifest_body_hash(manifest) != manifest.manifest_hash:
        raise ReproducibilityError(f"run {manifest.run_id} : manifeste altéré")
