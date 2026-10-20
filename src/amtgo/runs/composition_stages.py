"""Étapes de composition (M4) : ``measure_composition:<mesh>`` puis ``ontology_ensemble``.

Les champs de composition portent des attributs de groupe : leur classe d'accès
est au moins CONTROLLED, quelle que soit celle des sources (prompt §50, 06 §10).
Ils ne sont jamais exportés publiquement ; le rapport n'en contient que des
agrégats de domaine et des distances entre ontologies.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import numpy as np
import shapely
from shapely.strtree import STRtree

from amtgo.core.enums import EvidenceStatus, PrivacyClass
from amtgo.core.provenance import ProvenanceRecord
from amtgo.data.ingestion import read_observations
from amtgo.errors import ConfigurationError
from amtgo.measurement import composition as comp
from amtgo.measurement import fields as fields_mod
from amtgo.measurement.likelihoods import MeshIndex
from amtgo.measurement.validation import aggregation_weights, ground_truth_world
from amtgo.ontology import crosswalk as cwmod
from amtgo.ontology import ensemble
from amtgo.runs import artifacts
from amtgo.utils.canonical import content_hash

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


def _ctx_objects(ctx: StageContext) -> tuple[comp.CompositionManifest, dict[str, Any]]:
    m = ctx.manifest.composition_model
    if m is None:
        raise ConfigurationError("aucun modèle de composition dans ce run")
    return m, {o.ontology_id: o for o in ctx.manifest.ontology_set}


def _reference_polygons(ctx: StageContext) -> list[Any]:
    from amtgo.runs.measure_stages import _reference_polygons as ref

    return ref(ctx)


def _truth_reference(ctx: StageContext, idx_polys: list[Any], categories: list[str]) -> np.ndarray | None:
    """Parts vraies par polygone de référence, si (et seulement si) le monde est synthétique."""
    from amtgo.data.synthetic_world import composition, group_layer
    from amtgo.geo.crs import to_equal_area

    manifests = [s.manifest for s in ctx.manifest.data_manifest]
    world = ground_truth_world(manifests)
    if world is None:
        return None
    layer = group_layer(manifests[0].retrieval.parameters["world"])
    if layer is None or list(layer.categories) != categories:
        return None
    pts, _ = world.quadrature
    dens = world.density(pts)
    cmp_ = composition(world, layer, pts)
    tree = STRtree([to_equal_area(p) for p in idx_polys])
    pi, gi = tree.query(shapely.points(pts), predicate="intersects")
    out = np.zeros((len(idx_polys), len(categories)))
    seen = set()
    for p, g in sorted(zip(pi.tolist(), gi.tolist(), strict=True)):
        if p in seen:
            continue
        seen.add(p)
        out[g] += dens[p] * cmp_[p]
    return np.asarray(out / np.maximum(out.sum(axis=1, keepdims=True), 1e-12))


def measure_composition(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    m, ontologies = _ctx_objects(ctx)
    mm = ctx.manifest.measurement_model
    if mm is None:
        raise ConfigurationError("la composition exige le champ de population (M3) du même run")
    src = next((s for s in ctx.manifest.data_manifest if s.manifest.source_id == m.source_id), None)
    if src is None or comp.ROLE_COMPOSITION not in src.use.roles:
        raise ConfigurationError(f"rôle {comp.ROLE_COMPOSITION!r} non déclaré pour {m.source_id}")
    observed = ontologies[m.observed_ontology]
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    obs = read_observations(ctx.observations_path(m.source_id))
    level = mm.sampling.interval_level
    ctx.check_stop(f"measure_composition {mesh_id}")
    fit = comp.fit_composition(mesh, obs, m, observed, str(src.manifest.source_uuid),
                               mm.sampling.n_samples, mm.sampling.seed)
    fits = {observed.ontology_id: fit}
    for proj, cw in zip(m.projections, ctx.manifest.crosswalks, strict=True):
        ctx.check_stop(f"measure_composition {mesh_id} {proj.ontology}")
        target = ontologies[proj.ontology]
        mats = cwmod.sample_matrices(cw, observed, target, mm.sampling.n_samples, mm.sampling.seed)
        fits[target.ontology_id] = comp.project(fit, mats, target)

    population = fields_mod.read_field(ctx.run_dir, mesh_id)[2].astype(np.float64)
    idx = MeshIndex(mesh)
    ref_polys = _reference_polygons(ctx)
    weights = aggregation_weights(idx, ref_polys)
    per_ontology: dict[str, Any] = {}
    eng: dict[str, np.ndarray] = {}
    for oid, f in fits.items():
        res = ensemble.reference_summary(f.samples, population, weights, f.categories, level)
        res.update(comp.summary(f, level))
        per_ontology[oid] = res
        # Le nombre effectif se compare hors masse UNMAPPED, renormalisée.
        shares = f.samples[..., : len(ontologies[oid].leaf_ids)]
        shares = shares / np.maximum(shares.sum(axis=-1, keepdims=True), 1e-12)
        eng[oid] = np.median(comp.effective_number(comp.aggregate_shares(shares, population, weights)), axis=0)
    stability = ensemble.ontology_stability(eng)

    # Calibration (monde synthétique seulement), à l'échelle de référence et sur les cellules informées.
    truth = _truth_reference(ctx, ref_polys, fit.categories)
    calibration: dict[str, Any] = {"status": "not_available", "reason": "pas de vérité terrain"}
    if truth is not None:
        agg = comp.aggregate_shares(fit.samples, population, weights)
        a = (1 - level) / 2
        lo, hi = np.quantile(agg, a, axis=0), np.quantile(agg, 1 - a, axis=0)
        calibration = {"status": "done", "level": level,
                       "reference_coverage": float(((truth >= lo) & (truth <= hi)).mean()),
                       "reference_mean_abs_error": float(np.abs(agg.mean(axis=0) - truth).mean())}

    label_check = _historical_label_check(ctx, m, fits, population, idx, level)

    # Artefacts : résumés par cellule et tirages compressés, CONTROLLED (jamais publics).
    d = ctx.run_dir / "fields" / mesh_id
    for oid, f in fits.items():
        buf = io.BytesIO()
        np.savez_compressed(buf, samples=f.samples.astype(np.float16), categories=np.array(f.categories))
        tmp = d / f"composition__{oid}.npz.part"
        tmp.write_bytes(buf.getvalue())
        tmp.replace(d / f"composition__{oid}.npz")
    privacy = PrivacyClass.most_restrictive([src.manifest.privacy_class, PrivacyClass.CONTROLLED])
    meta = {
        "mesh_id": mesh_id, "model": m.content_hash, "evidence_status": EvidenceStatus.MODEL.value,
        "privacy_class": privacy.value, "ontologies": per_ontology, "ontology_stability": stability,
        "calibration": calibration, "historical_label_check": label_check,
        "samples_hash": content_hash({oid: float(np.round(f.samples.mean(), 6)) for oid, f in fits.items()}),
    }
    artifacts.write_json(ctx.run_dir, f"fields/{mesh_id}/composition.json", meta)
    record = ProvenanceRecord.create(
        "composition.fit_project",
        [f"field:{fields_mod.read_field(ctx.run_dir, mesh_id)[0]['field_id']}", f"composition:{m.content_hash}",
         *[f"ontology:{o.content_hash}" for o in ontologies.values()],
         *[f"crosswalk:{cw.content_hash}" for cw in ctx.manifest.crosswalks]],
        [f"composition:{mesh_id}:{content_hash(meta)}"], run_id=ctx.manifest.run_id,
    )
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    return {"count": len(fits), "detail": f"S_ontology={stability['s_ontology']:.2f}"}


def _historical_label_check(ctx: StageContext, m: comp.CompositionManifest, fits: dict[str, Any],
                            population: np.ndarray, idx: MeshIndex, level: float) -> dict[str, Any]:
    """Part de population que couvre l'étiquette unique d'une carte historique, par bloc.

    Mesure la *compression* d'une source historique, sans jamais attribuer d'étiquette.
    """
    for vs in m.validation_sources:
        src = next((s for s in ctx.manifest.data_manifest if s.manifest.source_id == vs.source_id), None)
        if src is None or comp.ROLE_ONTOLOGY_VALIDATION not in src.use.roles:
            continue
        obs = [o for o in read_observations(ctx.observations_path(vs.source_id)) if o.variable_id == vs.variable_id]
        by_ont: dict[str, list[Any]] = {}
        for o in obs:
            by_ont.setdefault(str(o.ontology_id), []).append(o)
        out = {}
        for oid, items in by_ont.items():
            f = fits.get(oid)
            if f is None:
                continue
            polys = [o.geometry() for o in items]
            agg = comp.aggregate_shares(f.samples, population, aggregation_weights(idx, polys))
            covered = []
            for b, o in enumerate(items):
                k = f.categories.index(o.attributes["label"])
                covered.append(float(agg[:, b, k].mean()))
            out[oid] = {"blocks": len(items), "mean_label_share": float(np.mean(covered)),
                        "min_label_share": float(np.min(covered))}
        return {"status": "done", "source_id": vs.source_id, **out}
    return {"status": "not_available", "reason": "aucune source de validation déclarée"}


def ontology_ensemble(ctx: StageContext, _: str) -> dict[str, Any]:
    """Synthèse : S^ontology par maillage et sur l'ensemble (min), pour le rapport et le gel."""
    per_mesh = {d.mesh_id: artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/composition.json")
                for d in ctx.manifest.mesh_set}
    vals = [v["ontology_stability"]["s_ontology"] for v in per_mesh.values()]
    finite = [v for v in vals if v == v]
    result = {"s_ontology_by_mesh": {k: v["ontology_stability"]["s_ontology"] for k, v in per_mesh.items()},
              "s_ontology": min(finite) if finite else float("nan")}
    artifacts.write_json(ctx.run_dir, "artifacts/ontology_ensemble.json", result)
    return {"detail": f"S_ontology={result['s_ontology']:.2f}"}
