"""Persistance du registre (runs, provenance, sources, observations, maillages).

Les artefacts de run (fichiers sous ``/state/runs``) restent la trace complète et
reprenable d'un run ; la base est le *registre interrogeable*. Toutes les
écritures sont des upserts sur identifiants stables : rejouer une étape ne
duplique rien.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import Engine, text

from amtgo.candidates.model import TerritoryCandidate
from amtgo.causal.model import CausalEffect
from amtgo.core.provenance import ProvenanceRecord
from amtgo.data.observations import Observation
from amtgo.data.sources import Source, SourceManifest
from amtgo.geo.mesh import Mesh
from amtgo.institutions.regimes import ConstitutionalRegime
from amtgo.manifests.run import RunManifest
from amtgo.ontology.model import Ontology, OntologyCrosswalk
from amtgo.scenarios.model import Scenario

if TYPE_CHECKING:
    from amtgo.measurement.fields import LatentFieldMeta

# Taille des lots d'insertion : borne mémoire, pas paramètre scientifique.
BATCH = 500


class Repository(Protocol):
    def record_run(self, manifest: RunManifest) -> None: ...
    def record_provenance(self, records: Sequence[ProvenanceRecord]) -> None: ...
    def record_source(self, manifest: SourceManifest, source: Source) -> None: ...
    def record_observations(self, observations: Iterable[Observation]) -> None: ...
    def record_mesh(self, mesh: Mesh) -> None: ...
    def record_latent_field(self, run_id: uuid.UUID, mesh: Mesh, meta: LatentFieldMeta,
                            rows: list[dict[str, Any]]) -> None: ...
    def record_measurement_freeze(self, run_id: uuid.UUID, freeze_hash: str) -> None: ...
    def record_ontologies(self, ontologies: Sequence[Ontology], crosswalks: Sequence[OntologyCrosswalk]) -> None: ...
    def record_regimes_scenarios(self, regimes: Sequence[ConstitutionalRegime],
                                 scenarios: Sequence[Scenario]) -> None: ...
    def record_causal_library(self, run_id: uuid.UUID, effects: Sequence[CausalEffect], freeze_hash: str) -> None: ...
    def record_candidates(self, run_id: uuid.UUID, mesh: Mesh, candidates: Sequence[TerritoryCandidate],
                          assignments: dict[str, Any]) -> None: ...
    def record_solutions(self, run_id: uuid.UUID, regime_id: str, archive: dict[str, Any]) -> None: ...
    def record_validation(self, run_id: uuid.UUID, report: dict[str, Any]) -> None: ...
    def record_transitions(self, run_id: uuid.UUID, product: dict[str, Any]) -> None: ...


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

    def record_latent_field(self, run_id: uuid.UUID, mesh: Mesh, meta: LatentFieldMeta,
                            rows: list[dict[str, Any]]) -> None:
        pass

    def record_measurement_freeze(self, run_id: uuid.UUID, freeze_hash: str) -> None:
        pass

    def record_ontologies(self, ontologies: Sequence[Ontology], crosswalks: Sequence[OntologyCrosswalk]) -> None:
        pass

    def record_regimes_scenarios(self, regimes: Sequence[ConstitutionalRegime],
                                 scenarios: Sequence[Scenario]) -> None:
        pass

    def record_causal_library(self, run_id: uuid.UUID, effects: Sequence[CausalEffect], freeze_hash: str) -> None:
        pass

    def record_candidates(self, run_id: uuid.UUID, mesh: Mesh, candidates: Sequence[TerritoryCandidate],
                          assignments: dict[str, Any]) -> None:
        pass

    def record_solutions(self, run_id: uuid.UUID, regime_id: str, archive: dict[str, Any]) -> None:
        pass

    def record_validation(self, run_id: uuid.UUID, report: dict[str, Any]) -> None:
        pass

    def record_transitions(self, run_id: uuid.UUID, product: dict[str, Any]) -> None:
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
                "scenario_set": json.dumps([{"scenario_id": sc.scenario_id, "content_hash": sc.content_hash}
                                            for sc in manifest.scenario_set]),
                "solver": json.dumps(None if manifest.optimizer_model is None
                                     else manifest.optimizer_model.model_dump(mode="json")),
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

    def record_latent_field(self, run_id: uuid.UUID, mesh: Mesh, meta: LatentFieldMeta,
                            rows: list[dict[str, Any]]) -> None:
        with self.engine.begin() as cx:
            cx.execute(text("""
                INSERT INTO latent_fields (field_id, run_id, mesh_id, definition_hash, variable_id,
                    time_period, measurement_hash, model_version, evidence_status, privacy_class,
                    computability, summary, samples_hash)
                VALUES (:fid, :run, :mesh, :dhash, :var, daterange(:p0, :p1, '[]'), :mhash, :mver,
                    CAST(:ev AS evidence_status), CAST(:priv AS privacy_class), :comp,
                    CAST(:summary AS jsonb), :shash)
                ON CONFLICT (field_id) DO NOTHING
            """), {
                "fid": meta.field_id, "run": run_id, "mesh": mesh.mesh_id,
                "dhash": mesh.definition.definition_hash, "var": meta.variable_id,
                "p0": meta.period["start"], "p1": meta.period["end"], "mhash": meta.measurement_hash,
                "mver": meta.model_version, "ev": meta.evidence_status.value,
                "priv": meta.privacy_class.value, "comp": meta.computability.value,
                "summary": json.dumps({"total": meta.total, "used": meta.used, "excluded": meta.excluded,
                                       "median_information_ratio": meta.median_information_ratio}),
                "shash": meta.samples_hash,
            })
        sql = text("""
            INSERT INTO latent_field_cells (field_id, cell_id, mean, sd, lower_bound, upper_bound,
                information_ratio, negative_fraction, computability)
            VALUES (:fid, :cell, :mean, :sd, :lo, :hi, :info, :neg, :comp)
            ON CONFLICT (field_id, cell_id) DO NOTHING
        """)
        for batch in _batches(rows):
            with self.engine.begin() as cx:
                cx.execute(sql, [{
                    "fid": meta.field_id, "cell": r["cell_id"], "mean": r["mean"], "sd": r["sd"],
                    "lo": r["lower"], "hi": r["upper"], "info": r["information_ratio"],
                    "neg": r["negative_fraction"], "comp": r["computability"],
                } for r in batch])

    def record_measurement_freeze(self, run_id: uuid.UUID, freeze_hash: str) -> None:
        with self.engine.begin() as cx:
            cx.execute(text("UPDATE run_manifests SET measurement_hash = :h WHERE run_id = :r "
                            "AND (measurement_hash IS NULL OR measurement_hash = :h)"),
                       {"h": freeze_hash, "r": run_id})

    def record_ontologies(self, ontologies: Sequence[Ontology], crosswalks: Sequence[OntologyCrosswalk]) -> None:
        with self.engine.begin() as cx:
            for o in ontologies:
                cx.execute(text("""
                    INSERT INTO ontologies (ontology_id, content_hash, version, name, dimension, kind,
                        evidence_status, definition)
                    VALUES (:id, :h, :v, :name, :dim, :kind, CAST(:ev AS evidence_status), CAST(:d AS jsonb))
                    ON CONFLICT DO NOTHING
                """), {"id": o.ontology_id, "h": o.content_hash, "v": o.version, "name": o.name,
                       "dim": o.dimension.value, "kind": o.kind.value, "ev": o.evidence_status.value,
                       "d": o.model_dump_json()})
                cx.execute(text("""
                    INSERT INTO ontology_concepts (ontology_id, content_hash, concept_id, source_label,
                        definition, parent_id, historical_period, self_identified, external_label)
                    VALUES (:id, :h, :c, :label, :d, :parent,
                        CASE WHEN CAST(:p0 AS date) IS NULL AND CAST(:p1 AS date) IS NULL THEN NULL
                             ELSE daterange(CAST(:p0 AS date), CAST(:p1 AS date), '[]') END, :si, :el)
                    ON CONFLICT DO NOTHING
                """), [{"id": o.ontology_id, "h": o.content_hash, "c": c.concept_id, "label": c.source_label,
                        "d": c.definition, "parent": c.parent_id, "p0": c.period_start, "p1": c.period_end,
                        "si": c.self_identified, "el": c.external_label} for c in o.concepts])
            for cw in crosswalks:
                cx.execute(text("""
                    INSERT INTO ontology_crosswalk (crosswalk_id, content_hash, source_ontology,
                        target_ontology, source_concept, target_concept, probability, concentration, evidence)
                    VALUES (:id, :h, :so, :to, :sc, :tc, :p, :conc, CAST(:ev AS jsonb))
                    ON CONFLICT DO NOTHING
                """), [{"id": cw.crosswalk_id, "h": cw.content_hash, "so": cw.source_ontology,
                        "to": cw.target_ontology, "sc": row.source_concept, "tc": t, "p": p,
                        "conc": row.concentration, "ev": json.dumps({"evidence": row.evidence})}
                       for row in cw.rows for t, p in row.targets.items()])

    def record_regimes_scenarios(self, regimes: Sequence[ConstitutionalRegime],
                                 scenarios: Sequence[Scenario]) -> None:
        with self.engine.begin() as cx:
            for r in regimes:
                cx.execute(text("""
                    INSERT INTO constitutional_regimes (regime_id, content_hash, name, version,
                        mobility_rules, fiscal_transfer_rules, defence_rules, market_rules, resource_rules,
                        infrastructure_rules, declared_border)
                    VALUES (:id, :h, :name, :v, CAST(:mob AS jsonb), CAST(:fis AS jsonb), CAST(:def AS jsonb),
                        CAST(:mkt AS jsonb), CAST(:res AS jsonb), CAST(:inf AS jsonb), CAST(:bor AS jsonb))
                    ON CONFLICT DO NOTHING
                """), {"id": r.regime_id.value, "h": r.content_hash, "name": r.name, "v": r.version,
                       "mob": r.mobility_rules.model_dump_json(), "fis": r.fiscal_transfer_rules.model_dump_json(),
                       "def": r.defence_rules.model_dump_json(), "mkt": r.market_rules.model_dump_json(),
                       "res": r.resource_rules.model_dump_json(), "inf": r.infrastructure_rules.model_dump_json(),
                       "bor": r.declared_border.model_dump_json()})
            for sc in scenarios:
                cx.execute(text("""
                    INSERT INTO scenarios (scenario_id, content_hash, version, mobility_regime, horizon_years,
                        population, climate, urbanization, economy, migration, infrastructure, security)
                    VALUES (:id, :h, :v, :mr, :hz, CAST(:pop AS jsonb), CAST(:cli AS jsonb), CAST(:urb AS jsonb),
                        CAST(:eco AS jsonb), CAST(:mig AS jsonb), CAST(:inf AS jsonb), CAST(:sec AS jsonb))
                    ON CONFLICT DO NOTHING
                """), {"id": sc.scenario_id, "h": sc.content_hash, "v": sc.version,
                       "mr": sc.mobility_regime.value, "hz": sc.horizon_years,
                       "pop": sc.population.model_dump_json(), "cli": sc.climate.model_dump_json(),
                       "urb": sc.urbanization.model_dump_json(), "eco": sc.economy.model_dump_json(),
                       "mig": sc.migration.model_dump_json(), "inf": sc.infrastructure.model_dump_json(),
                       "sec": sc.security.model_dump_json()})

    def record_causal_library(self, run_id: uuid.UUID, effects: Sequence[CausalEffect], freeze_hash: str) -> None:
        with self.engine.begin() as cx:
            for e in effects:
                cx.execute(text("""
                    INSERT INTO causal_effects (effect_id, content_hash, effect_key, treatment_definition,
                        outcome_definition, estimand, source_context, target_context, design, identification_grade,
                        effect_distribution, time_horizon, spillover_model, transportability, overlap_score,
                        mechanism, diagnostics, frozen_release)
                    VALUES (:id, :h, :k, CAST(:tr AS jsonb), CAST(:oc AS jsonb), :est, :sc, :tc, :d, :g,
                        CAST(:dist AS jsonb), CAST(:hz AS jsonb), CAST(:sp AS jsonb), :tp, :ov, CAST(:mech AS jsonb),
                        CAST(:diag AS jsonb), :rel)
                    ON CONFLICT DO NOTHING
                """), {"id": e.effect_id, "h": e.content_hash, "k": e.effect_key,
                       "tr": e.treatment.model_dump_json(), "oc": e.outcome.model_dump_json(), "est": e.estimand,
                       "sc": e.source_context, "tc": e.target_context, "d": e.design.value, "g": e.grade.value,
                       "dist": e.effect.model_dump_json(exclude={"samples"}),
                       "hz": json.dumps({"years": e.time_horizon_years}),
                       "sp": json.dumps({"model": e.spillover_model}), "tp": e.transport_status.value,
                       "ov": e.overlap, "mech": json.dumps({"description": e.mechanism}),
                       "diag": json.dumps({"diagnostics": {k: v.value for k, v in e.diagnostics.items()},
                                           "robustness": e.robustness}), "rel": freeze_hash})
                cx.execute(text("""
                    INSERT INTO causal_freezes (run_id, freeze_hash, effect_id, content_hash)
                    VALUES (:r, :f, :id, :h) ON CONFLICT DO NOTHING
                """), {"r": run_id, "f": freeze_hash, "id": e.effect_id, "h": e.content_hash})
            cx.execute(text("UPDATE run_manifests SET causal_library_hash = :h WHERE run_id = :r "
                            "AND (causal_library_hash IS NULL OR causal_library_hash = :h)"),
                       {"h": freeze_hash, "r": run_id})

    def record_candidates(self, run_id: uuid.UUID, mesh: Mesh, candidates: Sequence[TerritoryCandidate],
                          assignments: dict[str, Any]) -> None:
        from shapely import make_valid
        from shapely.geometry import MultiPolygon
        from shapely.ops import unary_union

        from amtgo.geo.families import polygonal_part
        from amtgo.utils.canonical import stable_uuid

        geoms = [c.geometry for c in mesh.cells.values()]
        rows = []
        for cand in candidates:
            if cand.duplicate_of is not None:
                continue  # même géométrie qu'un candidat déjà enregistré
            assign = assignments[cand.candidate_id]
            for label in range(cand.n_states):
                union = polygonal_part(make_valid(unary_union([g for g, a in zip(geoms, assign, strict=True)
                                                               if a == label])))
                if union is None:
                    continue
                multi = union if isinstance(union, MultiPolygon) else MultiPolygon([union])
                tid = stable_uuid("territory", [str(run_id), cand.candidate_id, label])
                rows.append({"tid": tid, "cid": cand.candidate_id,
                             "r": run_id, "m": mesh.mesh_id, "lv": cand.level, "lb": label, "g": multi.wkt,
                             "meth": cand.method, "fam": cand.family.value,
                             "seed": json.dumps(cand.params, sort_keys=True)})
        with self.engine.begin() as cx:
            for batch in _batches(rows):
                cx.execute(text("""
                    INSERT INTO territory_candidates (territory_id, candidate_id, run_id, mesh_id, level, label,
                        geometry, generation_method, family, seed, active)
                    VALUES (:tid, :cid, :r, :m, :lv, :lb, ST_GeomFromText(:g, 4326), :meth, :fam, :seed, false)
                    ON CONFLICT (territory_id) DO NOTHING
                """), batch)

    def record_solutions(self, run_id: uuid.UUID, regime_id: str, archive: dict[str, Any]) -> None:
        from amtgo.utils.canonical import stable_uuid

        rows = [{"id": stable_uuid("solution", [str(run_id), s["key"]]), "r": run_id, "reg": regime_id,
                 "k": s["key"], "fam": s["family"], "st": archive["recommendation_status"], "f": s["feasible"],
                 "rank": s["rank"], "m": json.dumps(s["objectives"]),
                 "stab": json.dumps({"s_ontology": s["s_ontology"], "s_scale": s["s_scale"],
                                     "s_publish": s["s_publish"]}),
                 "cs": json.dumps({"note": "efficacités I7 ; aucun effet territorial identifié"}),
                 "p": archive["privacy_class"]} for s in archive["solutions"]]
        with self.engine.begin() as cx:
            for batch in _batches(rows):
                cx.execute(text("""
                    INSERT INTO solutions (solution_id, run_id, regime_id, variant_key, family, status, feasible,
                        pareto_rank, metrics, stability, causal_support, privacy_status)
                    VALUES (:id, :r, :reg, :k, :fam, CAST(:st AS recommendation_status), :f, :rank,
                        CAST(:m AS jsonb), CAST(:stab AS jsonb), CAST(:cs AS jsonb), CAST(:p AS privacy_class))
                    ON CONFLICT (solution_id) DO NOTHING
                """), batch)

    def record_validation(self, run_id: uuid.UUID, report: dict[str, Any]) -> None:
        details = {"M": report["gate_m"], "C": {}, "O": {"goodhart": report["goodhart"]["status"]},
                   "S": {"public_layers": report["privacy"]["public_layers"]},
                   "R": {"s_publish": report["s_publish"], "tau": report["s_publish_tau"],
                         "single_mesh_dependent": report["multiscale"]["single_mesh_dependent"]}}
        rows = [{"r": run_id, "g": g, "s": s, "d": json.dumps(details[g])} for g, s in report["gates"].items()]
        with self.engine.begin() as cx:
            cx.execute(text("""
                INSERT INTO validation_gates (run_id, gate, status, detail)
                VALUES (:r, :g, :s, CAST(:d AS jsonb))
                ON CONFLICT (run_id, gate) DO UPDATE SET status = EXCLUDED.status, detail = EXCLUDED.detail
            """), rows)
            cx.execute(text("""
                UPDATE solutions SET status = CAST(:c AS recommendation_status),
                    stability = stability || CAST(:stab AS jsonb)
                WHERE run_id = :r
            """), {"r": run_id, "c": report["publication_category"],
                   "stab": json.dumps({"validated": True})})

    def record_transitions(self, run_id: uuid.UUID, product: dict[str, Any]) -> None:
        from amtgo.utils.canonical import stable_uuid

        rows = [{"id": stable_uuid("transition", [str(run_id), p["path_id"], str(s["step"])]), "r": run_id,
                 "sol": stable_uuid("solution", [str(run_id), p["target_key"]]), "p": p["path_id"],
                 "st": s["step"], "a": s["action"], "pl": json.dumps(s["payload"]),
                 "c": json.dumps({"cost": s["cost"], "uncertainty": s["uncertainty"], "violations": s["violations"]}),
                 "i": s["irreversibility"], "v": s["value_of_information"], "rank": p["rank"], "f": p["feasible"]}
                for p in product["paths"] for s in p["steps"]]
        with self.engine.begin() as cx:
            for batch in _batches(rows):
                cx.execute(text("""
                    INSERT INTO transitions (transition_id, run_id, solution_id, path_id, step, action_type,
                        action_payload, cost_distribution, irreversibility, value_of_information, path_rank,
                        path_feasible)
                    VALUES (:id, :r, :sol, :p, :st, CAST(:a AS transition_action), CAST(:pl AS jsonb),
                        CAST(:c AS jsonb), :i, :v, :rank, :f)
                    ON CONFLICT (transition_id) DO NOTHING
                """), batch)
