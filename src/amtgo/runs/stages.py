"""Étapes d'un run M0–M2. Chacune est bornée, idempotente et reprenable.

Ordre canonique (prompt §8), tronqué à ce qui existe :
``validate_sources`` → ``ingest:<source>`` … → ``build_mesh:<mesh>`` … →
``multiscale_check`` → ``report``. Les étapes suivantes (mesure, ontologies,
causalité, candidats, optimisation) n'existent pas encore : le rapport le dit,
et le statut de recommandation reste NOT_IDENTIFIABLE.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.ops import unary_union

from amtgo.core.enums import ComputabilityClass, RecommendationStatus, SupportType
from amtgo.core.provenance import ProvenanceRecord
from amtgo.data.ingestion import IngestRequest, ingest_source, read_observations
from amtgo.db.repository import Repository
from amtgo.errors import ConfigurationError, StageInterrupted, TopologyError
from amtgo.geo.mesh import BBoxExtent, Mesh, MeshDefinition, assert_valid_mesh, bbox_geometry
from amtgo.geo.multiscale import area_weighted_transfer, coverage_ratio
from amtgo.geo.ops import create_base_mesh
from amtgo.geo.support import allocate_point_masses
from amtgo.manifests.run import RunManifest, verify_manifest
from amtgo.runs import artifacts, measure_stages
from amtgo.runs.report import render_report


@dataclass
class StageContext:
    run_dir: Path
    manifest: RunManifest
    repo: Repository
    cache_dir: Path
    should_stop: Callable[[], bool]

    def check_stop(self, what: str) -> None:
        if self.should_stop():
            raise StageInterrupted(what)

    def observations_path(self, source_id: str) -> Path:
        return self.run_dir / "artifacts" / f"observations__{source_id}.parquet"


def plan_steps(manifest: RunManifest) -> list[str]:
    steps = ["validate_sources"]
    steps += [f"ingest:{s.manifest.source_id}" for s in manifest.data_manifest]
    steps += [f"build_mesh:{m.mesh_id}" for m in manifest.mesh_set]
    steps += ["multiscale_check"]
    if manifest.measurement_model is not None:
        steps += [f"measure:{m.mesh_id}" for m in manifest.mesh_set]
        steps += [f"validate_measurement:{m.mesh_id}" for m in manifest.mesh_set]
        steps += ["compare_fields", "measurement_freeze"]
    steps += ["report"]
    return steps


# --- étapes --------------------------------------------------------------------


def validate_sources(ctx: StageContext, _: str) -> dict[str, Any]:
    verify_manifest(ctx.manifest)
    for s in ctx.manifest.data_manifest:
        for role in s.use.roles:
            s.manifest.require_role(role)
        s.manifest.require_license(redistribute=s.use.redistribute, commercial=False)
    ctx.repo.record_run(ctx.manifest)
    return {"count": len(ctx.manifest.data_manifest)}


def ingest(ctx: StageContext, source_id: str) -> dict[str, Any]:
    resolved = next((s for s in ctx.manifest.data_manifest if s.manifest.source_id == source_id), None)
    if resolved is None:
        raise ConfigurationError(f"source {source_id} absente du manifeste")
    result = ingest_source(
        resolved.manifest,
        IngestRequest(roles=resolved.use.roles, redistribute=resolved.use.redistribute),
        cache_dir=ctx.cache_dir,
        out_dir=ctx.run_dir / "artifacts",
        run_id=ctx.manifest.run_id,
        should_stop=ctx.should_stop,
    )
    ctx.repo.record_source(resolved.manifest, result.source)
    ctx.repo.record_provenance(result.records)
    ctx.repo.record_observations(read_observations(result.observations_path))
    artifacts.write_provenance(ctx.run_dir, result.records)
    artifacts.write_json(ctx.run_dir, f"artifacts/source__{source_id}.json", {
        "source": result.source.model_dump(mode="json", exclude={"created_at"}),
        "observation_count": result.observation_count,
        "observations_hash": result.observations_hash,
    })
    return {"count": result.observation_count, "source_id": source_id}


def _extent_for(ctx: StageContext, definition: MeshDefinition) -> tuple[Any, list[str]]:
    if isinstance(definition.extent, BBoxExtent):
        return bbox_geometry(definition.extent), [f"bbox:{list(definition.extent.bbox)}"]
    ext = definition.extent
    path = ctx.observations_path(ext.source_id)
    if not path.exists():
        raise ConfigurationError(f"{definition.mesh_id} : source {ext.source_id} non ingérée")
    geoms = [o.geometry() for o in read_observations(path) if o.variable_id == ext.variable_id]
    if not geoms:
        raise TopologyError(f"{definition.mesh_id} : aucune géométrie {ext.variable_id}")
    meta = artifacts.read_json(ctx.run_dir, f"artifacts/source__{ext.source_id}.json")
    return unary_union(geoms), [meta["source"]["id"], f"observations:{meta['observations_hash']}"]


def build_mesh(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    definition = next((m for m in ctx.manifest.mesh_set if m.mesh_id == mesh_id), None)
    if definition is None:
        raise ConfigurationError(f"maillage {mesh_id} absent du manifeste")
    extent, inputs = _extent_for(ctx, definition)
    ctx.check_stop(f"build_mesh {mesh_id}")
    mesh = create_base_mesh(definition, extent)
    assert_valid_mesh(mesh)
    artifacts.write_mesh(ctx.run_dir, mesh)
    record = ProvenanceRecord.create(
        "geo.create_base_mesh", inputs, [f"mesh:{mesh_id}:{mesh.cells_hash}"],
        parameters={"definition_hash": definition.definition_hash}, run_id=ctx.manifest.run_id,
    )
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_mesh(mesh)
    ctx.repo.record_provenance([record])
    return {"count": len(mesh), "mesh_id": mesh_id}


def multiscale_check(ctx: StageContext, _: str) -> dict[str, Any]:
    """Contrôles de conservation inter-maillages (pas encore S_scale : aucune partition avant M8)."""
    meshes: dict[str, Mesh] = {m.mesh_id: artifacts.read_mesh(ctx.run_dir, m.mesh_id)
                               for m in ctx.manifest.mesh_set}
    point_obs = []
    for s in ctx.manifest.data_manifest:
        for o in read_observations(ctx.observations_path(s.manifest.source_id)):
            if o.support_type in (SupportType.POINT, SupportType.UNCERTAIN_POINT) and o.value:
                point_obs.append(o)
    result: dict[str, Any] = {"meshes": {}, "transfers": []}
    allocations = {}
    for mid, mesh in meshes.items():
        ctx.check_stop(f"multiscale_check {mid}")
        entry: dict[str, Any] = {"cells": len(mesh), "total_area_km2": round(mesh.total_area_km2, 6),
                                 "extent_coverage": round(coverage_ratio(mesh), 6)}
        if point_obs:
            alloc = allocate_point_masses(point_obs, mesh)
            allocations[mid] = alloc
            entry["point_mass_in"] = round(alloc.total_in, 6)
            entry["point_mass_unallocated"] = round(alloc.unallocated, 6)
        result["meshes"][mid] = entry
    ids = sorted(allocations)
    for a in ids:
        for b in ids:
            if a >= b:
                continue
            ctx.check_stop("multiscale_check transfers")
            t = area_weighted_transfer(allocations[a].values, meshes[a], meshes[b])
            result["transfers"].append({
                "from": a, "to": b, "mass_in": round(t.total_in, 6),
                "mass_out": round(t.total_out, 6), "unallocated": round(t.unallocated, 6),
            })
    artifacts.write_json(ctx.run_dir, "artifacts/multiscale.json", result)
    return {"count": len(meshes)}


def _round_sig(x: float, digits: int = 6) -> float:
    """Arrondi à ``digits`` chiffres significatifs : tolérance numérique de reproductibilité."""
    return float(f"{x:.{digits}g}")


def _measurement_summary(ctx: StageContext) -> dict[str, Any]:
    from amtgo.measurement.fields import read_field

    per_mesh: dict[str, Any] = {}
    for d in ctx.manifest.mesh_set:
        meta, _, _ = read_field(ctx.run_dir, d.mesh_id)
        val = artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/validation.json")
        per_mesh[d.mesh_id] = {"field": meta, "validation": val}
    # Classe la plus défavorable entre maillages : une conclusion ne vaut que si elle tient partout.
    classes = [ComputabilityClass(v["field"]["computability"]) for v in per_mesh.values()]
    worst = min(classes, key=lambda c: "DCBA".index(c.value)) if classes else ComputabilityClass.D
    comparison = artifacts.read_json(ctx.run_dir, "artifacts/fields_comparison.json")
    freeze = artifacts.read_json(ctx.run_dir, "measurement_freeze.json")
    outputs = {
        "freeze_hash": freeze["freeze_hash"],
        "totals": {k: {kk: _round_sig(vv) for kk, vv in v["field"]["total"].items()}
                   for k, v in sorted(per_mesh.items())},
        "computability": {k: v["field"]["computability"] for k, v in sorted(per_mesh.items())},
    }
    return {"per_mesh": per_mesh, "comparison": comparison, "freeze": freeze,
            "computability": worst, "outputs": outputs}


def report(ctx: StageContext, _: str) -> dict[str, Any]:
    status = RecommendationStatus.NOT_IDENTIFIABLE
    computability = ComputabilityClass.D
    sources = {s.manifest.source_id: artifacts.read_json(ctx.run_dir, f"artifacts/source__{s.manifest.source_id}.json")
               for s in ctx.manifest.data_manifest}
    meshes = {m.mesh_id: artifacts.read_json(ctx.run_dir, f"meshes/{m.mesh_id}/mesh.json")
              for m in ctx.manifest.mesh_set}
    multiscale = artifacts.read_json(ctx.run_dir, "artifacts/multiscale.json")
    measurement = _measurement_summary(ctx) if ctx.manifest.measurement_model else None
    if measurement is not None:
        computability = measurement["computability"]
    outputs = {
        "observations": {k: v["observations_hash"] for k, v in sorted(sources.items())},
        "meshes": {k: v["cells_hash"] for k, v in sorted(meshes.items())},
        "multiscale": multiscale,
        "measurement": None if measurement is None else measurement["outputs"],
        "recommendation_status": status.value,
        "computability_class": computability.value,
    }
    from amtgo.utils.canonical import content_hash

    outputs["outputs_hash"] = content_hash(outputs)
    artifacts.write_json(ctx.run_dir, "outputs.json", outputs)
    text = render_report(ctx.manifest, sources, meshes, multiscale, status, computability,
                         outputs["outputs_hash"], artifacts.read_provenance(ctx.run_dir), measurement)
    from amtgo.runs.state import write_json_atomic

    write_json_atomic(ctx.run_dir / "report.md", text)
    return {"detail": status.value}


STAGES: dict[str, Callable[[StageContext, str], dict[str, Any]]] = {
    "validate_sources": validate_sources,
    "ingest": ingest,
    "build_mesh": build_mesh,
    "multiscale_check": multiscale_check,
    "measure": measure_stages.measure,
    "validate_measurement": measure_stages.validate_measurement,
    "compare_fields": measure_stages.compare_fields,
    "measurement_freeze": measure_stages.measurement_freeze,
    "report": report,
}


def run_step(ctx: StageContext, step: str) -> dict[str, Any]:
    kind, _, arg = step.partition(":")
    try:
        fn = STAGES[kind]
    except KeyError as exc:
        raise ConfigurationError(f"étape inconnue : {step}") from exc
    return fn(ctx, arg)
