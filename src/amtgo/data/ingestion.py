"""Pipeline d'ingestion (M1) : licence → récupération → checksum → normalisation → provenance.

Les contrôles de licence et de privacy précèdent tout accès aux données : une
source dont l'usage prévu est incompatible n'est même pas téléchargée.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from amtgo.core.enums import EvidenceStatus, PrivacyClass
from amtgo.core.provenance import ProvenanceRecord
from amtgo.core.quality import QualityVector
from amtgo.core.uncertainty import UncertainValue
from amtgo.data.adapters import get_adapter
from amtgo.data.observations import Observation
from amtgo.data.sources import Source, SourceManifest
from amtgo.errors import ForbiddenSourceRole, PrivacyViolation, ProvenanceError, StageInterrupted
from amtgo.utils.canonical import content_hash


@dataclass(frozen=True)
class IngestRequest:
    """Usage prévu de la source dans ce run : vérifié contre licence et rôles."""

    roles: tuple[str, ...]
    redistribute: bool = False
    commercial: bool = False


@dataclass(frozen=True)
class IngestResult:
    source: Source
    observation_count: int
    observations_path: Path
    observations_hash: str
    records: tuple[ProvenanceRecord, ...]


def ingest_source(
    manifest: SourceManifest,
    request: IngestRequest,
    cache_dir: Path,
    out_dir: Path,
    run_id: uuid.UUID | None = None,
    should_stop: Callable[[], bool] = lambda: False,
    recorded_at: datetime | None = None,
) -> IngestResult:
    # 1. Licence et rôle AVANT toute récupération (prompt §68).
    if not request.roles:
        raise ForbiddenSourceRole(f"{manifest.source_id} : aucun rôle déclaré pour l'ingestion")
    for role in request.roles:
        manifest.require_role(role)
    manifest.require_license(redistribute=request.redistribute, commercial=request.commercial)

    adapter = get_adapter(manifest.retrieval.adapter)
    files: dict[str, Path] = {}
    checksums: dict[str, str] = {}
    # 2. Récupération et intégrité.
    for ref in adapter.discover(manifest):
        if should_stop():
            raise StageInterrupted(f"ingest {manifest.source_id} interrompu")
        path = adapter.fetch(manifest, ref, cache_dir)
        checksums[ref.name] = adapter.validate(manifest, ref, path)
        files[ref.name] = path

    retrieved_at = recorded_at or datetime.now(UTC)
    source = Source.from_manifest(manifest, retrieved_at, content_hash(checksums))

    # 3. Normalisation, avec garde-fous sur chaque observation.
    observations = list(adapter.normalize(manifest, files, retrieved_at))
    for obs in observations:
        _check_observation(manifest, source, obs)

    # 4. Écriture atomique et provenance.
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"observations__{manifest.source_id}.parquet"
    write_observations(observations, path)
    obs_hash = observations_content_hash(observations)

    records = (
        ProvenanceRecord.create(
            "ingest.fetch_validate",
            input_ids=[f"manifest:{manifest.content_hash}"],
            output_ids=[str(source.id)],
            parameters={"checksums": checksums, "adapter": manifest.retrieval.adapter},
            run_id=run_id,
        ),
        ProvenanceRecord.create(
            "ingest.normalize",
            input_ids=[str(source.id)],
            output_ids=[f"observations:{obs_hash}"],
            parameters={"count": len(observations), "roles": list(request.roles)},
            run_id=run_id,
        ),
    )
    return IngestResult(source, len(observations), path, obs_hash, records)


def _check_observation(manifest: SourceManifest, source: Source, obs: Observation) -> None:
    if obs.source_id != str(source.id):
        raise ProvenanceError(f"observation {obs.id} rattachée à une autre source")
    if obs.sensitivity.rank < manifest.privacy_class.rank:
        # Une observation ne peut pas être moins protégée que sa source.
        raise PrivacyViolation(
            f"observation {obs.id} : sensibilité {obs.sensitivity.value} < source "
            f"{manifest.privacy_class.value}"
        )
    if obs.evidence_status.strength > manifest.default_evidence_status.strength:
        # Aucune promotion silencieuse du statut de preuve (prompt §11).
        raise ProvenanceError(
            f"observation {obs.id} : statut {obs.evidence_status.name} plus fort que celui "
            f"de la source ({manifest.default_evidence_status.name})"
        )


# --- sérialisation ------------------------------------------------------------

_SCHEMA = pa.schema([
    ("observation_id", pa.string()),
    ("version", pa.string()),
    ("source_id", pa.string()),
    ("variable_id", pa.string()),
    ("ontology_id", pa.string()),
    ("support_type", pa.string()),
    ("geometry_wkt", pa.string()),
    ("raster_ref", pa.string()),
    ("admin_code", pa.string()),
    ("displacement_km", pa.float64()),
    ("valid_from", pa.timestamp("us", tz="UTC")),
    ("valid_until", pa.timestamp("us", tz="UTC")),
    ("recorded_at", pa.timestamp("us", tz="UTC")),
    ("value_json", pa.string()),
    ("attributes_json", pa.string()),
    ("quality_json", pa.string()),
    ("evidence_status", pa.string()),
    ("sensitivity", pa.string()),
])


def _row(o: Observation) -> dict[str, object]:
    return {
        "observation_id": str(o.id),
        "version": o.version,
        "source_id": o.source_id,
        "variable_id": o.variable_id,
        "ontology_id": o.ontology_id,
        "support_type": o.support_type.value,
        "geometry_wkt": o.geometry_wkt,
        "raster_ref": o.raster_ref,
        "admin_code": o.admin_code,
        "displacement_km": o.displacement_km,
        "valid_from": o.valid_from,
        "valid_until": o.valid_until,
        "recorded_at": o.recorded_at,
        "value_json": o.value.model_dump_json() if o.value else None,
        "attributes_json": json.dumps(o.attributes, sort_keys=True, ensure_ascii=False),
        "quality_json": o.quality.model_dump_json(),
        "evidence_status": o.evidence_status.value,
        "sensitivity": o.sensitivity.value,
    }


def write_observations(observations: Iterable[Observation], path: Path) -> None:
    rows = [_row(o) for o in sorted(observations, key=lambda o: str(o.id))]
    table = pa.Table.from_pylist(rows, schema=_SCHEMA)
    tmp = path.with_suffix(".parquet.part")
    pq.write_table(table, tmp)
    tmp.replace(path)


def read_observations(path: Path) -> list[Observation]:
    out = []
    for r in pq.read_table(path).to_pylist():
        out.append(Observation(
            id=r["observation_id"],
            version=r["version"],
            source_id=r["source_id"],
            variable_id=r["variable_id"],
            ontology_id=r["ontology_id"],
            support_type=r["support_type"],
            geometry_wkt=r["geometry_wkt"],
            raster_ref=r["raster_ref"],
            admin_code=r["admin_code"],
            displacement_km=r["displacement_km"],
            valid_from=r["valid_from"],
            valid_until=r["valid_until"],
            recorded_at=r["recorded_at"],
            value=UncertainValue.model_validate_json(r["value_json"]) if r["value_json"] else None,
            attributes=json.loads(r["attributes_json"]),
            quality=QualityVector.model_validate_json(r["quality_json"]),
            evidence_status=EvidenceStatus(r["evidence_status"]),
            sensitivity=PrivacyClass(r["sensitivity"]),
        ))
    return out


def observations_content_hash(observations: Iterable[Observation]) -> str:
    """Empreinte du contenu scientifique, sans horodatage d'enregistrement.

    ``recorded_at`` et ``created_at`` changent d'une exécution à l'autre ; ils
    sont exclus pour que « même manifeste ⇒ même résultat » soit vérifiable.
    """
    payload = [
        {k: v for k, v in _row(o).items() if k != "recorded_at"}
        for o in sorted(observations, key=lambda o: str(o.id))
    ]
    return content_hash(payload)
