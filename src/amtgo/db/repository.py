"""Persistance du registre (runs, provenance, sources, observations, maillages).

Les artefacts de run (fichiers sous ``/state/runs``) restent la trace complète et
reprenable d'un run ; la base est le *registre interrogeable*. Toutes les
écritures sont des upserts sur identifiants stables : rejouer une étape ne
duplique rien.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Protocol

from sqlalchemy import Engine, text

from amtgo.core.provenance import ProvenanceRecord
from amtgo.data.observations import Observation
from amtgo.data.sources import Source, SourceManifest
from amtgo.geo.mesh import Mesh
from amtgo.manifests.run import RunManifest

# Taille des lots d'insertion : borne mémoire, pas paramètre scientifique.
BATCH = 500


class Repository(Protocol):
    def record_run(self, manifest: RunManifest) -> None: ...
    def record_provenance(self, records: Sequence[ProvenanceRecord]) -> None: ...
    def record_source(self, manifest: SourceManifest, source: Source) -> None: ...
    def record_observations(self, observations: Iterable[Observation]) -> None: ...
    def record_mesh(self, mesh: Mesh) -> None: ...


class NullRepository:
    """Base désactivée (tests unitaires, smoke test) : les artefacts fichiers suffisent."""

    def record_run(self, manifest: RunManifest) -> None:
        pass

    def record_provenance(self, records: Sequence[ProvenanceRecord]) -> None:
        pass

    def record_source(self, manifest: SourceManifest, source: Source) -> None:
        pass

    def record_observations(self, observations: Iterable[Observation]) -> None:
        pass

    def record_mesh(self, mesh: Mesh) -> None:
        pass


def _batches[T](items: Iterable[T], n: int = BATCH) -> Iterable[list[T]]:
    batch: list[T] = []
    for it in items:
        batch.append(it)
        if len(batch) >= n:
            yield batch
            batch = []
    if batch:
        yield batch


class PostgresRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def record_run(self, manifest: RunManifest) -> None:
        with self.engine.begin() as cx:
            cx.execute(text("""
                INSERT INTO run_manifests (run_id, manifest_hash, manifest, code_commit, code_version,
                    data_manifest_hash, normative_manifest_hash, constitutional_regime, mesh_set,
                    scenario_set, solver_manifest, measurement_hash, causal_library_hash, created_at)
                VALUES (:run_id, :manifest_hash, CAST(:manifest AS jsonb), :code_commit, :code_version,
                    :data_manifest_hash, :normative_hash, :regime, CAST(:mesh_set AS jsonb),
                    CAST(:scenario_set AS jsonb), CAST(:solver AS jsonb), NULL, NULL, :created_at)
                ON CONFLICT (run_id) DO NOTHING
            """), {
                "run_id": manifest.run_id,
                "manifest_hash": manifest.manifest_hash,
                "manifest": manifest.model_dump_json(),
                "code_commit": manifest.code_commit,
                "code_version": manifest.code_version,
                "data_manifest_hash": manifest.data_manifest_hash,
                "normative_hash": manifest.normative_manifest_hash,
                "regime": manifest.constitutional_regime.regime_id.value,
                "mesh_set": json.dumps([m.model_dump(mode="json") for m in manifest.mesh_set]),
                "scenario_set": json.dumps(list(manifest.scenario_set)),
                "solver": json.dumps(manifest.solver),
                "created_at": manifest.created_at,
            })

    def record_provenance(self, records: Sequence[ProvenanceRecord]) -> None:
        if not records:
            return
        with self.engine.begin() as cx:
            cx.execute(text("""
                INSERT INTO provenance_records (record_id, transformation, input_ids, output_ids,
                    code_version, parameters, run_id, created_at)
                VALUES (:record_id, :transformation, :input_ids, :output_ids, :code_version,
                    CAST(:parameters AS jsonb), :run_id, :created_at)
                ON CONFLICT (record_id) DO NOTHING
            """), [{
                "record_id": r.record_id, "transformation": r.transformation,
                "input_ids": list(r.input_ids), "output_ids": list(r.output_ids),
                "code_version": r.code_version, "parameters": json.dumps(r.parameters, default=str),
                "run_id": r.run_id, "created_at": r.timestamp,
            } for r in records])

    def record_source(self, manifest: SourceManifest, source: Source) -> None:
        lic = manifest.license
        with self.engine.begin() as cx:
            cx.execute(text("""
                INSERT INTO licenses (license_id, name, url, redistribution, commercial_use,
                    attribution_required, share_alike)
                VALUES (:id, :name, :url, :redis, :comm, :attr, :sa)
                ON CONFLICT (license_id) DO NOTHING
            """), {"id": lic.license_id, "name": lic.name, "url": lic.url, "redis": lic.redistribution,
                   "comm": lic.commercial_use, "attr": lic.attribution_required, "sa": lic.share_alike})
            cx.execute(text("""
                INSERT INTO sources (source_id, slug, name, provider, release, retrieved_at, url,
                    citation, license_id, method, temporal_start, temporal_end, privacy_class,
                    data_zone, roles_allowed, roles_forbidden, checksum, manifest_hash, manifest)
                VALUES (:id, :slug, :name, :provider, :release, :retrieved_at, :url, :citation,
                    :license_id, :method, :t0, :t1, CAST(:privacy AS privacy_class),
                    CAST(:zone AS data_zone), :allowed, :forbidden, :checksum, :mhash,
                    CAST(:manifest AS jsonb))
                ON CONFLICT (source_id) DO UPDATE SET retrieved_at = EXCLUDED.retrieved_at
                    WHERE sources.checksum = EXCLUDED.checksum
            """), {
                "id": source.id, "slug": manifest.source_id, "name": manifest.name,
                "provider": manifest.provider, "release": manifest.release,
                "retrieved_at": source.retrieved_at, "url": manifest.url,
                "citation": manifest.citation, "license_id": lic.license_id,
                "method": manifest.method, "t0": manifest.temporal_start, "t1": manifest.temporal_end,
                "privacy": manifest.privacy_class.value, "zone": manifest.data_zone.value,
                "allowed": list(manifest.roles.allowed), "forbidden": list(manifest.roles.forbidden),
                "checksum": source.checksum, "mhash": manifest.content_hash,
                "manifest": manifest.model_dump_json(),
            })

    def record_observations(self, observations: Iterable[Observation]) -> None:
        sql = text("""
            INSERT INTO observations (observation_id, source_id, variable_id, ontology_id,
                support_type, geometry, raster_ref, admin_code, displacement_km, valid_from,
                valid_until, recorded_at, value, attributes, quality, evidence_status, sensitivity)
            VALUES (:id, :source_id, :variable_id, :ontology_id, CAST(:support AS support_type),
                CASE WHEN CAST(:wkt AS text) IS NULL THEN NULL
                     ELSE ST_GeomFromText(CAST(:wkt AS text), 4326) END,
                :raster_ref, :admin_code, :displacement_km, :valid_from, :valid_until, :recorded_at,
                CAST(:value AS jsonb), CAST(:attributes AS jsonb), CAST(:quality AS jsonb),
                CAST(:evidence AS evidence_status), CAST(:sensitivity AS privacy_class))
            ON CONFLICT (observation_id) DO NOTHING
        """)
        for batch in _batches(observations):
            with self.engine.begin() as cx:
                cx.execute(sql, [{
                    "id": o.id, "source_id": o.source_id, "variable_id": o.variable_id,
                    "ontology_id": o.ontology_id, "support": o.support_type.value,
                    "wkt": o.geometry_wkt, "raster_ref": o.raster_ref, "admin_code": o.admin_code,
                    "displacement_km": o.displacement_km, "valid_from": o.valid_from,
                    "valid_until": o.valid_until, "recorded_at": o.recorded_at,
                    "value": o.value.model_dump_json() if o.value else None,
                    "attributes": json.dumps(o.attributes, default=str),
                    "quality": o.quality.model_dump_json(),
                    "evidence": o.evidence_status.value, "sensitivity": o.sensitivity.value,
                } for o in batch])

    def record_mesh(self, mesh: Mesh) -> None:
        d = mesh.definition
        with self.engine.begin() as cx:
            cx.execute(text("""
                INSERT INTO mesh_definitions (mesh_id, definition_hash, family, resolution,
                    definition, cells_hash, cell_count)
                VALUES (:mesh_id, :dhash, :family, :res, CAST(:definition AS jsonb), :chash, :n)
                ON CONFLICT (mesh_id, definition_hash) DO NOTHING
            """), {"mesh_id": d.mesh_id, "dhash": d.definition_hash, "family": d.family.value,
                   "res": d.resolution, "definition": d.model_dump_json(),
                   "chash": mesh.cells_hash, "n": len(mesh)})
        sql = text("""
            INSERT INTO cells (mesh_id, definition_hash, cell_id, resolution, geometry,
                parent_cell_id, area_km2, clipped)
            VALUES (:mesh_id, :dhash, :cell_id, :res, ST_Multi(ST_GeomFromText(:wkt, 4326)), :parent,
                :area, :clipped)
            ON CONFLICT (mesh_id, definition_hash, cell_id) DO NOTHING
        """)
        for batch in _batches(mesh.cells.values()):
            with self.engine.begin() as cx:
                cx.execute(sql, [{
                    "mesh_id": d.mesh_id, "dhash": d.definition_hash, "cell_id": c.cell_id,
                    "res": c.resolution, "wkt": c.geometry.wkt, "parent": c.parent_cell_id,
                    "area": c.area_km2, "clipped": c.clipped,
                } for c in batch])
