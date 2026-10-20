"""Étapes M7 : ``causal_estimate:<effet>`` → ``causal_validate`` → ``causal_freeze``.

Ordre imposé (prompt §32) : measurement_freeze → causal_freeze → toute
évaluation qui consomme un effet. Les estimations portent sur des panels
ingérés dans le run ; leur validation (région exclue, placebo, contrôle négatif,
et vérité pour les sources synthétiques) est écrite dans les enregistrements
**avant** le gel. Après le gel, la bibliothèque n'est accessible qu'en lecture.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from shapely import STRtree

from amtgo.causal.did import NEVER, Panel, estimate, leave_region_out
from amtgo.causal.library import (
    CausalLibraryManifest,
    DiDEstimation,
    FrozenCausalLibrary,
    effect_from_json,
    effect_to_json,
    library_hash,
)
from amtgo.causal.model import CausalEffect, Design, IdentificationGrade, TransportStatus, widen
from amtgo.causal.transport import overlap, transport_status
from amtgo.core.enums import SupportType
from amtgo.core.provenance import ProvenanceRecord
from amtgo.data.ingestion import read_observations
from amtgo.data.sources import RetrievalKind
from amtgo.errors import ConfigurationError, InsufficientEvidence
from amtgo.geo.crs import to_equal_area
from amtgo.runs import artifacts
from amtgo.utils.canonical import content_hash

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


def _library(ctx: StageContext) -> CausalLibraryManifest:
    lib = ctx.manifest.causal_library
    if lib is None:
        raise ConfigurationError("aucune bibliothèque causale dans ce run")
    return lib


def _estimation(ctx: StageContext, key: str) -> DiDEstimation:
    est = next((e for e in _library(ctx).estimations if e.effect_key == key), None)
    if est is None:
        raise ConfigurationError(f"estimation {key} absente de la bibliothèque")
    return est


def _panel(ctx: StageContext, est: DiDEstimation) -> tuple[Panel, np.ndarray | None, list[Any], np.ndarray]:
    """Panel (unités triées), contrôle négatif, géométries et densités des unités."""
    obs = read_observations(ctx.observations_path(est.panel_source))
    def table(var: str) -> dict[tuple[str, int], Any]:
        return {(str(o.admin_code), o.valid_from.year): o for o in obs if o.variable_id == var}
    y_obs = table(est.outcome_variable)
    if not y_obs:
        raise InsufficientEvidence(f"{est.effect_key} : aucune observation {est.outcome_variable}")
    units = sorted({u for u, _ in y_obs})
    years = np.array(sorted({t for _, t in y_obs}))
    balanced = len(y_obs) == len(units) * len(years)
    if not balanced:
        raise InsufficientEvidence(f"{est.effect_key} : panel déséquilibré (composition variable)")

    def matrix(tab: dict[tuple[str, int], Any]) -> np.ndarray:
        return np.array([[tab[(u, int(t))].value.mean for t in years] for u in units])
    first = {u: y_obs[(u, int(years[0]))] for u in units}
    cohort = np.array([int(first[u].attributes.get("treatment_cohort", NEVER)) for u in units])
    density = np.array([float(first[u].attributes["density"]) for u in units])
    geoms = [first[u].geometry() for u in units]
    # Voisinage par arête partagée (un coin commun ne suffit pas) ; exposition = part des voisins traités.
    tree = STRtree(geoms)
    exposure = np.zeros(len(units))
    for i, g in enumerate(geoms):
        nb = [int(j) for j in tree.query(g, predicate="touches") if g.intersection(geoms[int(j)]).length > 0]
        exposure[i] = float(np.mean([cohort[j] != NEVER for j in nb])) if nb else 0.0
    nc = None
    if est.negative_control_variable:
        nc = matrix(table(est.negative_control_variable))
    return Panel(matrix(y_obs), years, cohort, exposure, balanced), nc, geoms, density


def _target_density(ctx: StageContext, source_id: str) -> np.ndarray:
    obs = [o for o in read_observations(ctx.observations_path(source_id))
           if o.support_type in (SupportType.ADMIN, SupportType.POLYGON) and o.value is not None
           and o.value.mean is not None and o.geometry() is not None and o.ontology_id is None]
    if not obs:
        raise InsufficientEvidence(f"transport : aucun polygone de population dans {source_id}")
    return np.array([float(o.value.mean) / (to_equal_area(o.geometry()).area / 1e6) for o in obs])  # type: ignore[union-attr, arg-type]


def causal_estimate(ctx: StageContext, key: str) -> dict[str, Any]:
    lib = _library(ctx)
    est = _estimation(ctx, key)
    rules = lib.diagnostics
    panel, nc, _, density = _panel(ctx, est)
    res = estimate(panel, rules.bootstrap_draws, ctx.manifest.seeds[0], rules.alpha, rules.interval_level,
                   negative_control=nc, placebo_shift=rules.placebo_shift_years)
    ov = overlap({"density": density}, {"density": _target_density(ctx, est.target_source)})
    transport = transport_status(ov, lib.transport.identified_overlap,
                                 ctx.manifest.normative_manifest.stability.overlap_min)
    effect = res.att if transport is not TransportStatus.PARTIAL else widen(res.att, lib.transport.partial_widening)
    record = CausalEffect(
        effect_key=key, treatment=est.treatment, outcome=est.outcome, source_context=est.source_context,
        target_context=est.target_context, estimand="ATT (agrégé, pondéré par cohorte)",
        design=Design.STAGGERED_DID, grade=IdentificationGrade.I3, effect=effect,
        time_horizon_years=float(panel.years[-1] - panel.years[0] + 1),
        spillover_model="exposition E_i = part des voisins traités (arête partagée), testée sur les témoins",
        mechanism=est.mechanism,
        transport_status=transport, overlap=ov, diagnostics=res.diagnostics, robustness=res.robustness,
        source_ids=(est.panel_source,))
    out = {"effect": effect_to_json(record),
           # Estimation brute, avant élargissement de transport : c'est elle que la vérité synthétique juge.
           "estimate": {"mean": res.att.mean, "lower": res.att.lower, "upper": res.att.upper},
           "event_study": {str(e): {"mean": v.mean, "lower": v.lower, "upper": v.upper}
                           for e, v in res.event_study.items()},
           "n_units": len(panel.cohort), "years": [int(panel.years[0]), int(panel.years[-1])]}
    artifacts.write_json(ctx.run_dir, f"artifacts/causal/{key}.json", out)
    failed = sorted(k for k, v in res.diagnostics.items() if v.value == "FAILED")
    return {"detail": f"ATT={res.att.mean:.3f} transport={transport.value} "
                      + (f"FAILED={','.join(failed)}" if failed else "diagnostics=PASSED")}


def causal_validate(ctx: StageContext, _: str) -> dict[str, Any]:
    """Validation (04 §21, 05 §8) : région exclue, placebo, contrôle négatif ; vérité si synthétique."""
    from amtgo.data.synthetic_world import PanelDesign, panel_true_att

    lib = _library(ctx)
    rules = lib.diagnostics
    by_src = {s.manifest.source_id: s.manifest for s in ctx.manifest.data_manifest}
    report: dict[str, Any] = {}
    for est in lib.estimations:
        art = artifacts.read_json(ctx.run_dir, f"artifacts/causal/{est.effect_key}.json")
        rec = effect_from_json(art["effect"])
        panel, _nc, geoms, _density = _panel(ctx, est)
        xs = np.array([g.centroid.x for g in geoms])
        region = xs > np.median(xs)
        entry: dict[str, Any] = {"admissibility": rec.admissibility(
            ctx.manifest.normative_manifest.stability.overlap_min).value}
        try:
            entry["leave_region_out"] = leave_region_out(panel, region, rules.bootstrap_draws,
                                                         ctx.manifest.seeds[0], rules.alpha, rules.interval_level)
        except ValueError as exc:  # une région sans témoin : la validation n'est pas faite, et c'est dit
            entry["leave_region_out"] = {"consistent": None, "reason": str(exc)}
        src = by_src[est.panel_source]
        if src.retrieval.kind is RetrievalKind.SYNTHETIC:
            truth = panel_true_att(PanelDesign.from_params(src.retrieval.parameters["panel"]),
                                   [int(c) for c in panel.cohort])
            raw = art["estimate"]
            covered = bool(raw["lower"] <= truth <= raw["upper"])
            entry["synthetic_truth"] = {"att": truth, "covered": covered}
        robustness = dict(rec.robustness)
        lro = entry["leave_region_out"].get("consistent")
        robustness["leave_region_out"] = "NOT_TESTED" if lro is None else ("PASSED" if lro else "FAILED")
        if "synthetic_truth" in entry:
            robustness["synthetic_truth_coverage"] = "PASSED" if entry["synthetic_truth"]["covered"] else "FAILED"
        rec = rec.model_copy(update={"robustness": robustness})
        art["effect"] = effect_to_json(CausalEffect.model_validate(rec.model_dump()))
        artifacts.write_json(ctx.run_dir, f"artifacts/causal/{est.effect_key}.json", art)
        entry["robustness"] = robustness
        report[est.effect_key] = entry
    # Gate C (05 §20) : tout effet admis doit passer chaque test de robustesse exécuté.
    admitted = {k: v for k, v in report.items() if v["admissibility"] != "UNSUPPORTED"}
    gate_ok = all(r != "FAILED" for v in admitted.values() for r in v["robustness"].values())
    result = {"estimations": report, "gate_c": "PASSED" if gate_ok else "FAILED",
              "admitted": sorted(admitted), "rejected": sorted(set(report) - set(admitted))}
    artifacts.write_json(ctx.run_dir, "artifacts/causal_validation.json", result)
    return {"detail": f"gate_C={result['gate_c']} admitted={len(admitted)}/{len(report)}"}


def causal_freeze(ctx: StageContext, _: str) -> dict[str, Any]:
    lib = _library(ctx)
    effects = [d.to_effect() for d in lib.declared]
    effects += [effect_from_json(artifacts.read_json(ctx.run_dir, f"artifacts/causal/{e.effect_key}.json")["effect"])
                for e in lib.estimations]
    freeze_hash = library_hash(effects)
    measurement = (artifacts.read_json(ctx.run_dir, "measurement_freeze.json")["freeze_hash"]
                   if (ctx.run_dir / "measurement_freeze.json").exists() else None)
    artifacts.write_json(ctx.run_dir, "artifacts/causal_library.json",
                         {"effects": [effect_to_json(e) for e in sorted(effects, key=lambda e: e.effect_key)]})
    artifacts.write_json(ctx.run_dir, "causal_freeze.json", {
        "freeze_hash": freeze_hash, "library_manifest": lib.content_hash, "measurement_freeze": measurement,
        "effects": {e.effect_key: e.content_hash for e in effects}})
    record = ProvenanceRecord.create(
        "causal.freeze", [f"causal_library:{lib.content_hash}"]
        + ([f"measurement_freeze:{measurement}"] if measurement else []),
        [f"causal_freeze:{freeze_hash}"], run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    ctx.repo.record_causal_library(ctx.manifest.run_id, effects, freeze_hash)
    return {"count": len(effects), "detail": freeze_hash[:19]}


def frozen_library(ctx: StageContext) -> FrozenCausalLibrary:
    """Bibliothèque gelée du run (lecture seule, empreinte vérifiée)."""
    lib = _library(ctx)
    freeze = artifacts.read_json(ctx.run_dir, "causal_freeze.json")
    stored = artifacts.read_json(ctx.run_dir, "artifacts/causal_library.json")["effects"]
    effects = [effect_from_json(d) for d in stored]
    return FrozenCausalLibrary(effects, freeze["freeze_hash"], ctx.manifest.normative_manifest.stability.overlap_min,
                               lib.novelty)


def library_summary(ctx: StageContext) -> dict[str, Any]:
    lib = frozen_library(ctx)
    region = ctx.manifest.request.region
    out = {}
    for k in lib.keys:
        rec = lib.record(k)
        ans = lib.query(k, region)
        out[k] = {"treatment": rec.treatment.component.value,
                  "outcome": f"{rec.outcome.kind.value}:{rec.outcome.variable}",
                  "design": rec.design.value, "grade": rec.grade.value, "transport": rec.transport_status.value,
                  "overlap": rec.overlap, "status": ans.status, "reason": ans.reason,
                  "effect": None if ans.effect is None else {"mean": ans.effect.mean, "lower": ans.effect.lower,
                                                             "upper": ans.effect.upper},
                  "diagnostics": {d: v.value for d, v in rec.diagnostics.items()},
                  "robustness": dict(rec.robustness)}
    return {"freeze_hash": lib.freeze_hash, "effects": out, "content_hash": content_hash(out)}
