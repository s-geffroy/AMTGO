"""Écriture et relecture des artefacts d'un run (fichiers dans le répertoire du run)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from shapely import wkt

from amtgo.core.provenance import ProvenanceRecord
from amtgo.geo.mesh import Cell, Mesh, MeshDefinition
from amtgo.runs.state import write_json_atomic
from amtgo.utils.canonical import canonical_json

_CELLS_SCHEMA = pa.schema([
    ("cell_id", pa.string()),
    ("resolution", pa.int32()),
    ("parent_cell_id", pa.string()),
    ("area_km2", pa.float64()),
    ("geometry_wkt", pa.string()),
    ("clipped", pa.bool_()),
])


def write_provenance(run_dir: Path, records: tuple[ProvenanceRecord, ...] | list[ProvenanceRecord]) -> None:
    """Un fichier par enregistrement, nommé par son id : réécrire est idempotent."""
    for r in records:
        write_json_atomic(run_dir / "provenance" / f"{r.record_id}.json", r.model_dump_json())


def read_provenance(run_dir: Path) -> list[ProvenanceRecord]:
    d = run_dir / "provenance"
    if not d.exists():
        return []
    return [ProvenanceRecord.model_validate_json(p.read_text()) for p in sorted(d.glob("*.json"))]


def write_mesh(run_dir: Path, mesh: Mesh) -> Path:
    d = run_dir / "meshes" / mesh.mesh_id
    d.mkdir(parents=True, exist_ok=True)
    rows = [
        {"cell_id": c.cell_id, "resolution": c.resolution, "parent_cell_id": c.parent_cell_id,
         "area_km2": c.area_km2, "geometry_wkt": c.geometry.wkt, "clipped": c.clipped}
        for c in mesh.cells.values()
    ]
    tmp = d / "cells.parquet.part"
    pq.write_table(pa.Table.from_pylist(rows, schema=_CELLS_SCHEMA), tmp)
    tmp.replace(d / "cells.parquet")
    meta = {
        "definition": mesh.definition.model_dump(mode="json"),
        "definition_hash": mesh.definition.definition_hash,
        "cells_hash": mesh.cells_hash,
        "cell_count": len(mesh),
        "total_area_km2": mesh.total_area_km2,
        "extent_wkt": mesh.extent.wkt,
    }
    write_json_atomic(d / "mesh.json", json.dumps(meta, indent=2, ensure_ascii=False))
    return d


def read_mesh(run_dir: Path, mesh_id: str) -> Mesh:
    d = run_dir / "meshes" / mesh_id
    meta = json.loads((d / "mesh.json").read_text())
    definition = MeshDefinition.model_validate(meta["definition"])
    cells: dict[str, Cell] = {}
    for r in pq.read_table(d / "cells.parquet").to_pylist():
        cells[r["cell_id"]] = Cell(r["cell_id"], r["resolution"], wkt.loads(r["geometry_wkt"]),
                                   r["area_km2"], r["parent_cell_id"], r["clipped"])
    return Mesh(definition, wkt.loads(meta["extent_wkt"]), cells)


def write_json(run_dir: Path, name: str, payload: Any) -> None:
    write_json_atomic(run_dir / name, json.dumps(json.loads(canonical_json(payload)), indent=2,
                                                 ensure_ascii=False, sort_keys=True))


def read_json(run_dir: Path, name: str) -> Any:
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


def write_bytes(run_dir: Path, name: str, data: bytes) -> None:
    """Écriture atomique d'un artefact binaire (tmp puis rename) : une étape interrompue ne laisse rien."""
    path = run_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)
