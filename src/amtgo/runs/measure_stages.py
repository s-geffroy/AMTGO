"""Étapes de mesure (M3) : ``measure:<mesh>`` → ``validate_measurement:<mesh>`` →
``compare_fields`` → ``measurement_freeze``.

Le gel (``measurement_freeze``, prompt §32) fige l'empreinte des champs et du
modèle de mesure. Les étapes ultérieures (causalité, optimisation) ne pourront
consommer que des champs gelés, et ne pourront pas les réestimer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from amtgo.core.enums import PrivacyClass
from amtgo.core.provenance import ProvenanceRecord
from amtgo.data.ingestion import read_observations
from amtgo.data.observations import Observation
from amtgo.errors import ConfigurationError, ProvenanceError
from amtgo.measurement import fields as fields_mod
from amtgo.measurement import raster_prior as raster_prior_mod
from amtgo.measurement import validation
from amtgo.measurement.engine import ROLE_MEASUREMENT, fit, require_observations
from amtgo.measurement.likelihoods import MeshIndex
from amtgo.measurement.manifest import MeasurementManifest, RasterLogNormalDensityPrior
from amtgo.runs import artifacts
from amtgo.utils.canonical import content_hash, file_sha256

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


def _manifest(ctx: StageContext) -> MeasurementManifest:
    m = ctx.manifest.measurement_model
    if m is None:
        raise ConfigurationError("aucun modèle de mesure dans ce run")
    return m


def _inputs(ctx: StageContext) -> tuple[list[Observation], dict[str, str], set[str], list[str], PrivacyClass]:
    m = _manifest(ctx)
    wanted = {lk.source_id for lk in m.likelihoods}
    observations: list[Observation] = []
    uuid_to_slug: dict[str, str] = {}
    roles: set[str] = set()
    hashes: list[str] = []
    classes = []
    for s in ctx.manifest.data_manifest:
        slug = s.manifest.source_id
        if slug not in wanted:
            continue
        uuid_to_slug[str(s.manifest.source_uuid)] = slug
        if ROLE_MEASUREMENT in s.use.roles:
            roles.add(slug)
        observations += read_observations(ctx.observations_path(slug))
        meta = artifacts.read_json(ctx.run_dir, f"artifacts/source__{slug}.json")
        hashes.append(f"observations:{meta['observations_hash']}")
        classes.append(s.manifest.privacy_class)
    return observations, uuid_to_slug, roles, sorted(hashes), PrivacyClass.most_restrictive(classes)


def _raster_prior_spec(ctx: StageContext) -> RasterLogNormalDensityPrior | None:
    p = _manifest(ctx).prior
    return p if isinstance(p, RasterLogNormalDensityPrior) else None


def raster_prior(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    """Densité a priori par cellule lue sur le raster épinglé (WorldPop), par bandes."""
    spec = _raster_prior_spec(ctx)
    if spec is None:
        raise ConfigurationError("aucun prior raster dans ce modèle de mesure")
    resolved = next(s for s in ctx.manifest.data_manifest if s.manifest.source_id == spec.source_id)
    rasters = [o for o in read_observations(ctx.observations_path(spec.source_id))
               if o.variable_id == spec.variable_id and o.raster_ref]
    if len(rasters) != 1:
        raise ConfigurationError(f"prior raster : une observation {spec.variable_id} attendue, {len(rasters)} trouvées")
    assert rasters[0].raster_ref is not None
    name, _, sha = rasters[0].raster_ref.partition("@")
    path = ctx.cache_dir / spec.source_id / resolved.manifest.release / name
    if not path.exists() or file_sha256(path) != sha:
        raise ProvenanceError(f"prior raster : {name} absent du cache ou différent de {sha[:19]}")
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    idx = MeshIndex(mesh)
    cells = raster_prior_mod.cell_totals(path, idx, spec.block_pixels, ctx.should_stop)
    density = raster_prior_mod.prior_density(cells, idx, spec.floor_density_per_km2)
    summary = raster_prior_mod.summary(cells, idx, spec.floor_density_per_km2)
    artifacts.write_json(ctx.run_dir, f"fields/{mesh_id}/prior.json", {
        "source_id": spec.source_id, "raster_ref": rasters[0].raster_ref, "cells_hash": mesh.cells_hash,
        "summary": summary, "density_per_km2": [float(d) for d in density]})
    record = ProvenanceRecord.create(
        "measurement.raster_prior", [rasters[0].raster_ref, f"mesh:{mesh_id}:{mesh.cells_hash}"],
        [f"prior:{mesh_id}:{content_hash([float(d) for d in density])}"],
        parameters={"block_pixels": spec.block_pixels, "floor_density_per_km2": spec.floor_density_per_km2},
        run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    return {"count": summary["cells"], "detail": f"plancher {summary['cells_at_floor']}"}


def prior_density(ctx: StageContext, mesh_id: str) -> np.ndarray | None:
    """Densités du prior raster de ce maillage (None si le prior n'est pas un raster)."""
    if _raster_prior_spec(ctx) is None:
        return None
    meta = artifacts.read_json(ctx.run_dir, f"fields/{mesh_id}/prior.json")
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    if meta["cells_hash"] != mesh.cells_hash:
        raise ProvenanceError(f"prior raster {mesh_id} calculé sur un autre maillage")
    return np.asarray(meta["density_per_km2"], dtype=float)


def measure(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    m = _manifest(ctx)
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    obs, slugs, roles, hashes, privacy = _inputs(ctx)
    ctx.check_stop(f"measure {mesh_id}")
    result = fit(mesh, obs, m, slugs, roles, prior_density(ctx, mesh_id))
    require_observations(result.selection)
    meta, rows = fields_mod.build_field(result, mesh_id, mesh.cells_hash, m, content_hash(hashes), privacy,
                                        str(ctx.manifest.run_id))
    fields_mod.write_field(ctx.run_dir, meta, rows, result.posterior.samples)
    record = ProvenanceRecord.create(
        "measurement.fuse", [*hashes, f"mesh:{mesh_id}:{mesh.cells_hash}", f"measurement:{m.content_hash}"],
        [f"field:{meta.field_id}"],
        parameters={"used": meta.used, "excluded": meta.excluded}, run_id=ctx.manifest.run_id,
    )
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    ctx.repo.record_latent_field(ctx.manifest.run_id, mesh, meta, rows)
    return {"count": meta.cells, "detail": meta.computability.value}


def validate_measurement(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    m = _manifest(ctx)
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    obs, slugs, roles, _, _ = _inputs(ctx)
    vctx = validation.FitContext.build(mesh, obs, m, slugs, roles, prior_density(ctx, mesh_id))
    manifests = [s.manifest for s in ctx.manifest.data_manifest if s.manifest.source_id in slugs.values()]
    out: dict[str, Any] = {}
    for name, fn in (("holdout", validation.holdout_check), ("ablation", validation.ablation),
                     ("disagreement", validation.disagreement)):
        ctx.check_stop(f"validate_measurement {mesh_id} {name}")
        out[name] = fn(vctx)
    ctx.check_stop(f"validate_measurement {mesh_id} calibration")
    out["calibration"] = validation.calibration(vctx, manifests)
    artifacts.write_json(ctx.run_dir, f"fields/{mesh_id}/validation.json", out)
    return {"count": len(out)}


# Grille de référence de la comparaison entre maillages : carrés LAEA de 100 km
# (base 400 km, niveau 2), indépendants des polygones administratifs servant de
# marges — sinon la comparaison serait triviale.
REFERENCE_GRID_BASE_KM = 400.0
REFERENCE_GRID_LEVEL = 2


def _reference_polygons(ctx: StageContext) -> list[Any]:
    from amtgo.geo.mesh import BBoxExtent, MeshDefinition, MeshFamily
    from amtgo.geo.ops import create_base_mesh

    first = artifacts.read_mesh(ctx.run_dir, ctx.manifest.mesh_set[0].mesh_id)
    bounds = first.extent.bounds
    ref = create_base_mesh(MeshDefinition(
        mesh_id="reference_grid", family=MeshFamily.GRID_LAEA, resolution=REFERENCE_GRID_LEVEL,
        grid_base_km=REFERENCE_GRID_BASE_KM, extent=BBoxExtent(bbox=bounds)), first.extent)
    return [c.geometry for c in ref.cells.values()]


def compare_fields(ctx: StageContext, _: str) -> dict[str, Any]:
    """Totaux sur une grille de référence reconstruits depuis chaque maillage (MAUP)."""
    polys = _reference_polygons(ctx)
    if not polys:
        result: dict[str, Any] = {"status": "not_available", "reason": "aucun polygone de référence"}
    else:
        per_mesh, info = {}, {}
        m = _manifest(ctx)
        for d in ctx.manifest.mesh_set:
            ctx.check_stop("compare_fields")
            mesh = artifacts.read_mesh(ctx.run_dir, d.mesh_id)
            idx = MeshIndex(mesh)
            samples = fields_mod.read_field(ctx.run_dir, d.mesh_id)[2]
            per_mesh[d.mesh_id] = validation.district_totals(samples, idx, polys)
            ratios = validation.scale_information(samples, idx, m, polys, prior_density(ctx, d.mesh_id))
            info[d.mesh_id] = {"median": float(np.median(ratios)),
                               "computability": fields_mod.cell_class(
                                   float(np.median(ratios)), 0.0, m.computability).value}
        result = {"status": "done", "polygons": len(polys), "reference_km": 100,
                  "reference_scale_information": info, **validation.compare_across_meshes(per_mesh)}
    artifacts.write_json(ctx.run_dir, "artifacts/fields_comparison.json", result)
    return {"count": len(ctx.manifest.mesh_set)}


def measurement_freeze(ctx: StageContext, _: str) -> dict[str, Any]:
    m = _manifest(ctx)
    entries = {}
    for d in ctx.manifest.mesh_set:
        fmeta = fields_mod.read_field(ctx.run_dir, d.mesh_id)[0]
        if fmeta["measurement_hash"] != m.content_hash:
            raise ProvenanceError(f"champ {d.mesh_id} produit par un autre modèle de mesure")
        entries[d.mesh_id] = {"field_id": fmeta["field_id"], "cells_hash": fmeta["cells_hash"],
                              "samples_hash": fmeta["samples_hash"]}
    compositions = {}
    if ctx.manifest.composition_model is not None:
        compositions = {
            d.mesh_id: content_hash(artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/composition.json"))
            for d in ctx.manifest.mesh_set}
    freeze = {"measurement_model": m.content_hash, "fields": entries, "compositions": compositions}
    freeze_hash = content_hash(freeze)
    artifacts.write_json(ctx.run_dir, "measurement_freeze.json", {**freeze, "freeze_hash": freeze_hash})
    record = ProvenanceRecord.create(
        "measurement.freeze", [f"field:{e['field_id']}" for e in entries.values()],
        [f"measurement_freeze:{freeze_hash}"], run_id=ctx.manifest.run_id,
    )
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    ctx.repo.record_measurement_freeze(ctx.manifest.run_id, freeze_hash)
    return {"detail": freeze_hash[:19]}
