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
from amtgo.runs import (
    artifacts,
    candidate_stages,
    causal_stages,
    composer_stages,
    composition_stages,
    dfi_stages,
    map_r_stages,
    measure_stages,
    optimizer_stages,
    validation_stages,
    viability_stages,
)
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


def _causal_steps(manifest: RunManifest) -> list[str]:
    """Estimation, validation et gel causal : après measurement_freeze, avant tout consommateur d'effet."""
    if manifest.causal_library is None:
        return []
    return ([f"causal_estimate:{e.effect_key}" for e in manifest.causal_library.estimations]
            + ["causal_validate", "causal_freeze"])


def plan_steps(manifest: RunManifest) -> list[str]:
    steps = ["validate_sources"]
    steps += [f"ingest:{s.manifest.source_id}" for s in manifest.data_manifest]
    steps += [f"build_mesh:{m.mesh_id}" for m in manifest.mesh_set]
    steps += ["multiscale_check"]
    if manifest.measurement_model is not None:
        steps += [f"measure:{m.mesh_id}" for m in manifest.mesh_set]
        steps += [f"validate_measurement:{m.mesh_id}" for m in manifest.mesh_set]
        steps += ["compare_fields"]
        if manifest.composition_model is not None:
            steps += [f"measure_composition:{m.mesh_id}" for m in manifest.mesh_set]
            steps += ["ontology_ensemble"]
        steps += ["measurement_freeze"]
        steps += _causal_steps(manifest)
        if manifest.dfi_model is not None:
            steps += [f"dfi:{m.mesh_id}" for m in manifest.mesh_set]
            steps += ["dfi_ensemble"]
        if manifest.viability_model is not None:
            steps += [f"viability:{m.mesh_id}" for m in manifest.mesh_set]
            steps += ["viability_ensemble"]
        if manifest.candidate_model is not None:
            steps += [f"candidates:{m.mesh_id}" for m in manifest.mesh_set]
            steps += ["candidate_ensemble"]
        if manifest.composer_model is not None:
            steps += [f"compose:{m.mesh_id}" for m in manifest.mesh_set]
            steps += ["compose_ensemble"]
        if manifest.optimizer_model is not None:
            steps += [f"evaluate_candidates:{m.mesh_id}" for m in manifest.mesh_set]
            steps += ["pareto", "validation"]
            if manifest.transition_model is not None:
                steps += ["map_r"]
    else:
        steps += _causal_steps(manifest)
    if any(sc.diagnostic_only for sc in manifest.scenario_set):
        steps += ["s2c_diagnostic"]
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
    ctx.repo.record_ontologies(ctx.manifest.ontology_set, ctx.manifest.crosswalks)
    regimes = {r.content_hash: r for r in (ctx.manifest.constitutional_regime, ctx.manifest.observed_regime,
                                           *ctx.manifest.regime_sensitivity) if r is not None}
    ctx.repo.record_regimes_scenarios(list(regimes.values()), ctx.manifest.scenario_set)
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
            # Masses de population seulement : une réponse d'identité (ontology_id) n'est pas un compte.
            if (o.support_type in (SupportType.POINT, SupportType.UNCERTAIN_POINT) and o.value
                    and o.ontology_id is None):
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


def _viability_output(a: dict[str, Any]) -> list[Any]:
    return [a["status"], None if a["coverage"] is None else _round_sig(a["coverage"]["mean"], 4)]


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
    composition = None
    if ctx.manifest.composition_model is not None:
        composition = {
            "per_mesh": {d.mesh_id: artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/composition.json")
                         for d in ctx.manifest.mesh_set},
            "ensemble": artifacts.read_json(ctx.run_dir, "artifacts/ontology_ensemble.json"),
        }
    dfi = None
    if ctx.manifest.dfi_model is not None:
        dfi = {"per_mesh": {d.mesh_id: artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/dfi.json")
                            for d in ctx.manifest.mesh_set},
               "ensemble": artifacts.read_json(ctx.run_dir, "artifacts/dfi_ensemble.json")}
    viability = None
    if ctx.manifest.viability_model is not None:
        viability = {"per_mesh": {d.mesh_id: artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/viability.json")
                                  for d in ctx.manifest.mesh_set},
                     "ensemble": artifacts.read_json(ctx.run_dir, "artifacts/viability_ensemble.json")}
    freeze = artifacts.read_json(ctx.run_dir, "measurement_freeze.json")
    outputs = {
        "freeze_hash": freeze["freeze_hash"],
        "totals": {k: {kk: _round_sig(vv) for kk, vv in v["field"]["total"].items()}
                   for k, v in sorted(per_mesh.items())},
        "computability": {k: v["field"]["computability"] for k, v in sorted(per_mesh.items())},
        "s_ontology": None if composition is None else _round_sig(composition["ensemble"]["s_ontology"]),
        "dfi": None if dfi is None else {
            k: {o: {kk: _round_sig(vv, 4) for kk, vv in x["headline"].items()} for o, x in v["ontologies"].items()}
            for k, v in sorted(dfi["per_mesh"].items())},
        "viability": None if viability is None else {
            k: {sid: {rid: {t: _viability_output(a) for t, a in by_t.items()} for rid, by_t in by_r.items()}
                for sid, by_r in v["assessments"].items()}
            for k, v in sorted(viability["per_mesh"].items())},
    }
    return {"per_mesh": per_mesh, "comparison": comparison, "freeze": freeze, "computability": worst,
            "outputs": outputs, "composition": composition, "dfi": dfi, "viability": viability}


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
    s2c = (artifacts.read_json(ctx.run_dir, "artifacts/s2c_diagnostic.json")
           if any(sc.diagnostic_only for sc in ctx.manifest.scenario_set) else None)
    cand = None
    if ctx.manifest.candidate_model is not None:
        cand = {"ensemble": artifacts.read_json(ctx.run_dir, "artifacts/candidate_ensemble.json"),
                "per_mesh": {d.mesh_id: artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/candidates.json")
                             for d in ctx.manifest.mesh_set}}
    if ctx.manifest.composer_model is not None and cand is not None:
        cand["composer"] = {
            "ensemble": artifacts.read_json(ctx.run_dir, "artifacts/institutional_ensemble.json"),
            "per_mesh": {d.mesh_id: artifacts.read_json(
                ctx.run_dir, f"fields/{d.mesh_id}/institutional_composition.json") for d in ctx.manifest.mesh_set}}
    if ctx.manifest.optimizer_model is not None and cand is not None:
        cand["pareto"] = artifacts.read_json(ctx.run_dir, "artifacts/pareto_archive.json")
        cand["validation"] = artifacts.read_json(ctx.run_dir, "artifacts/validation.json")
        # La catégorie de publication vient des gates (05 §20-21), jamais d'un défaut optimiste.
        status = RecommendationStatus(cand["validation"]["publication_category"])
        if ctx.manifest.transition_model is not None:
            cand["map_r"] = artifacts.read_json(ctx.run_dir, "artifacts/map_r.json")
    causal = None
    if ctx.manifest.causal_library is not None:
        causal = {**causal_stages.library_summary(ctx),
                  "validation": artifacts.read_json(ctx.run_dir, "artifacts/causal_validation.json")}
    outputs = {
        "observations": {k: v["observations_hash"] for k, v in sorted(sources.items())},
        "meshes": {k: v["cells_hash"] for k, v in sorted(meshes.items())},
        "multiscale": multiscale,
        "measurement": None if measurement is None else measurement["outputs"],
        "s2c": None if s2c is None else {k: v["status"] for k, v in sorted(s2c.items())},
        "candidates": None if cand is None else {
            k: {"s_scale": None if v["s_scale"] is None else _round_sig(v["s_scale"], 4),
                "n_states": v["n_states_by_mesh"]} for k, v in sorted(cand["ensemble"]["variants"].items())},
        "composer": None if cand is None or "composer" not in cand else {
            k: v for k, v in cand["composer"]["ensemble"].items() if k in ("conclusion", "chosen", "stability")},
        "pareto": None if cand is None or "pareto" not in cand else {
            "conclusion": cand["pareto"]["conclusion"], "gate_o": cand["pareto"]["gate_o"],
            "ranks": {s["key"]: s["rank"] for s in cand["pareto"]["solutions"]}},
        "validation": None if cand is None or "validation" not in cand else {
            k: cand["validation"][k] for k in ("conclusion", "gates", "publication_category", "release_allowed")},
        "map_r": None if cand is None or "map_r" not in cand else {
            "conclusion": cand["map_r"]["conclusion"], "first_level_on_front": cand["map_r"]["first_level_on_front"],
            "ranks": {p["path_id"]: p["rank"] for p in cand["map_r"]["paths"]}},
        "causal": None if causal is None else {
            "freeze_hash": causal["freeze_hash"], "gate_c": causal["validation"]["gate_c"],
            "status": {k: v["status"] for k, v in sorted(causal["effects"].items())}},
        "recommendation_status": status.value,
        "computability_class": computability.value,
    }
    from amtgo.utils.canonical import content_hash

    outputs["outputs_hash"] = content_hash(outputs)
    artifacts.write_json(ctx.run_dir, "outputs.json", outputs)
    text = render_report(ctx.manifest, sources, meshes, multiscale, status, computability,
                         outputs["outputs_hash"], artifacts.read_provenance(ctx.run_dir), measurement, s2c,
                         causal, cand)
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
    "measure_composition": composition_stages.measure_composition,
    "ontology_ensemble": composition_stages.ontology_ensemble,
    "measurement_freeze": measure_stages.measurement_freeze,
    "causal_estimate": causal_stages.causal_estimate,
    "causal_validate": causal_stages.causal_validate,
    "causal_freeze": causal_stages.causal_freeze,
    "dfi": dfi_stages.dfi,
    "dfi_ensemble": dfi_stages.dfi_ensemble,
    "viability": viability_stages.viability,
    "viability_ensemble": viability_stages.viability_ensemble,
    "s2c_diagnostic": viability_stages.s2c_diagnostic,
    "candidates": candidate_stages.candidates,
    "candidate_ensemble": candidate_stages.candidate_ensemble,
    "compose": composer_stages.compose_mesh,
    "compose_ensemble": composer_stages.compose_ensemble,
    "evaluate_candidates": optimizer_stages.evaluate_candidates,
    "pareto": optimizer_stages.pareto,
    "validation": validation_stages.validation,
    "map_r": map_r_stages.map_r,
    "report": report,
}


def run_step(ctx: StageContext, step: str) -> dict[str, Any]:
    kind, _, arg = step.partition(":")
    try:
        fn = STAGES[kind]
    except KeyError as exc:
        raise ConfigurationError(f"étape inconnue : {step}") from exc
    return fn(ctx, arg)
