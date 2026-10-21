"""Étape M12 ``map_r`` : produit Map-R régional (02 §20, §34 ; prompt §76-80 ; 06 §15-16).

Après la validation, on construit les trajectoires depuis le statu quo
(``optimization.transition``) et leur archive, coût de transition compris. Le
produit est le tuple de 02 §34 — ensemble de Pareto, incertitude, provenance,
support causal, régime normatif, options de transition — et non une carte :

- hiérarchie contrefactuelle (§79) : par niveau, les trajectoires et leur rang ;
- explication de chaque trajectoire du front face au statu quo (§80) ;
- formulation conditionnelle admise (06 §15) et date de validité (06 §16) ;
- couche cartographique : seulement si la validation permet une publication
  (ROBUST ou CONDITIONAL, tous gates passés) **et** si le privacy guard la laisse
  sortir ; sinon elle reste vide et dit pourquoi (§75-76 : pas de frontière nette).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from amtgo.causal.library import CausalAnswer
from amtgo.core.provenance import ProvenanceRecord
from amtgo.errors import ConfigurationError
from amtgo.optimization.archive import Archive, Variant, build, geometry_relation
from amtgo.optimization.objectives import OBJECTIVES
from amtgo.optimization.transition import (
    INSTITUTIONAL_FAMILY,
    PATH_OBJECTIVE,
    TERRITORIAL_FAMILY,
    ActionType,
    Path,
    Step,
    apply_urgency,
    conclusion,
    explain,
    institutional_paths,
    statement,
    status_quo_path,
    territorial_path,
)
from amtgo.privacy.guard import ExportLayer, evaluate_release
from amtgo.runs import artifacts
from amtgo.runs.causal_stages import frozen_library
from amtgo.runs.optimizer_stages import _s_ontology, normative_parameters, variants
from amtgo.utils.canonical import content_hash

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


def _urgent(ctx: StageContext) -> dict[str, int]:
    """Estimations de domination grave urgente au statu quo, par maillage|ontologie (02 §27)."""
    out = {}
    for d in ctx.manifest.mesh_set:
        dfi = artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/dfi.json")
        for o, res in dfi["ontologies"].items():
            out[f"{d.mesh_id}|{o}"] = int(res["domination"]["urgent"])
    return out


@dataclass
class RegionalPaths:
    """Trajectoires Map-R d'un run et leur archive (réutilisées par la coordination continentale, M14)."""

    paths: list[Path]
    variants: list[Variant]
    archive: Archive
    eps: dict[str, float]
    skipped: list[str]
    urgent: dict[str, int]
    affected: list[str]
    effects: dict[str, CausalAnswer]
    inst_key: str
    by_key: dict[str, dict[str, Any]]


def regional_paths(ctx: StageContext) -> RegionalPaths:
    tm, om, cm, dm = (ctx.manifest.transition_model, ctx.manifest.optimizer_model, ctx.manifest.composer_model,
                      ctx.manifest.dfi_model)
    if tm is None or om is None or cm is None or dm is None:
        raise ConfigurationError("Map-R exige les trajectoires, l'optimiseur, le composeur et D/F/I")
    nm = ctx.manifest.normative_manifest
    archive = artifacts.read_json(ctx.run_dir, "artifacts/pareto_archive.json")
    vs, _attacks, _evals = variants(ctx)
    by_key = {s["key"]: s for s in archive["solutions"]}
    sq = next(v for v in vs if v.family == "STATUS_QUO")
    inst_key = next(v.key for v in vs if v.family == "INSTITUTIONAL_ONLY_REFORM")
    composer = {}
    for d in ctx.manifest.mesh_set:
        comp = artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/institutional_composition.json")
        composer.update({(d.mesh_id, o): res for o, res in comp["ontologies"].items()})
    lib = frozen_library(ctx)
    region = ctx.manifest.request.region
    effects = {k: lib.query(k, region) for k in cm.effect_keys}

    paths = [status_quo_path(sq)]
    inst, skipped = institutional_paths(composer, sq, cm, effects, tm)
    paths += inst
    sq_states = by_key[sq.key]["n_states_by_mesh"]
    for v in vs:
        if v.baseline or by_key[v.key]["rank"] != 1:
            continue  # seules les cibles territoriales du front de l'archive validée
        creates = any(n > sq_states[m] for m, n in by_key[v.key]["n_states_by_mesh"].items())
        paths.append(territorial_path(v, by_key[v.key]["name"], creates, tm))
    urgent = _urgent(ctx)
    affected = apply_urgency(paths) if any(urgent.values()) else []

    pvs = [p.as_variant(nm.transition) for p in paths]
    # Géométrie de chaque trajectoire : sa cible territoriale, sinon la géométrie actuelle (M13).
    geometry = {p.path_id: p.target if p.family == TERRITORIAL_FAMILY else sq.key for p in paths}
    by_geom = {v.key: v for v in vs}
    for pv in pvs:
        for other in pvs:
            ga, gb = geometry[pv.key], geometry[other.key]
            if pv.key != other.key:
                pv.relations[other.key] = geometry_relation(by_geom[ga], by_geom[gb], sq.key)
    eps = {**om.epsilon, PATH_OBJECTIVE: tm.path_epsilon}
    objectives = (*OBJECTIVES, PATH_OBJECTIVE)
    a = build(pvs, eps, nm.robustness, normative_parameters(ctx), objectives, sq_comparison_excludes=())
    return RegionalPaths(paths, pvs, a, eps, skipped, urgent, affected, effects, inst_key, by_key)


def map_r(ctx: StageContext, _: str) -> dict[str, Any]:
    tm, cm, dm = ctx.manifest.transition_model, ctx.manifest.composer_model, ctx.manifest.dfi_model
    assert tm is not None and cm is not None and dm is not None
    nm = ctx.manifest.normative_manifest
    validation = artifacts.read_json(ctx.run_dir, "artifacts/validation.json")
    rp = regional_paths(ctx)
    paths, a, eps, by_key, effects = rp.paths, rp.archive, rp.eps, rp.by_key, rp.effects
    skipped, urgent, affected, inst_key = rp.skipped, rp.urgent, rp.affected, rp.inst_key
    lib = frozen_library(ctx)
    families = {p.path_id: p.family for p in paths}
    concl = conclusion(a.conclusion, a.improving, families)
    sols = {s.key: s for s in a.solutions}
    sq_sol = sols[paths[0].path_id]
    category = validation["publication_category"]
    regime = ctx.manifest.constitutional_regime.regime_id.value
    ontologies = [o.ontology_id for o in ctx.manifest.ontology_set]

    def robustness_of(p: Path) -> float | None:
        if p.family == TERRITORIAL_FAMILY:
            s_pub: float | None = validation["stability"][p.target]["s_publish"]
            return s_pub
        return None  # S^time inconnu : S^publish de toute trajectoire l'est aussi

    rows = []
    for p in paths:
        s = sols[p.path_id]
        support = []
        for st in p.steps:
            key = _effect_of(cm, st.payload.get("lever"))
            if key is not None:
                ans = effects[key]
                support.append(f"{key} : {ans.grade.value if ans.grade else ans.status}")
        if p.family == TERRITORIAL_FAMILY:
            support = ["aucun effet territorial identifié ; J_V et J_reif reposent sur des effets I7"]
        rows.append({
            "path_id": p.path_id, "family": p.family, "target": p.target,
            "target_key": inst_key if p.family == INSTITUTIONAL_FAMILY else p.target,
            "name": by_key[p.target]["name"] if p.family == TERRITORIAL_FAMILY else p.path_id.removeprefix("path:"),
            "steps": [st.as_json() for st in p.steps], "top_action": p.top_action.value,
            "penalty": p.penalty(nm.transition), "rank": s.rank, "feasible": s.feasible, "violated": s.violated,
            "objectives": s.objectives,
            "explanation": {**explain(s.objectives, sq_sol.objectives, eps),
                            "what_changes": [_describe(st) for st in p.steps],
                            "causal_support": support,
                            "uncertainty": {"s_ontology": _s_ontology(p.omega, dm.relative_floor),
                                            "s_publish": robustness_of(p), "s_time": validation["s_time"]},
                            "normative_assumptions": {
                                "regime": regime, "normative_manifest": nm.content_hash,
                                "political_choices": validation["sensitivity"]["political_choices"],
                                "regime_dependent": validation["regimes"]["regime_dependent"]}},
            "statement": statement(regime, ontologies, lib.freeze_hash, robustness_of(p), category, s.rank == 1)})
    rows.sort(key=lambda r: (r["rank"] or 99, r["path_id"]))
    hierarchy = []
    for t in ActionType:
        members = [r for r in rows if r["top_action"] == t.value]
        note = None
        if t is ActionType.BORDER_WEAKENING:
            note = ("non modélisé à l'échelle régionale : relève du régime continental (R2/R3), voir la "
                    "sensibilité de régime de la validation")
        hierarchy.append({"level": t.level, "action": t.value, "paths": [r["path_id"] for r in members],
                          "on_front": [r["path_id"] for r in members if r["rank"] == 1], "note": note})
    first_front = next((h["action"] for h in hierarchy if h["on_front"]), None)
    released = bool(validation["release_allowed"])
    layer = ExportLayer("map_r_candidates", nm.privacy.default_access, False, False, False,
                        sum(1 for r in rows if r["family"] == TERRITORIAL_FAMILY and r["rank"] == 1),
                        ("boundary",), "map_r", derived_from_group_attributes=True)
    decision = evaluate_release([layer], nm.privacy)[layer.name]
    vintages = sorted({str(s.manifest.temporal_start) for s in ctx.manifest.data_manifest
                       if s.manifest.temporal_start is not None})
    product = {
        "map_mode": ctx.manifest.request.map_mode.value, "conclusion": concl, "archive_conclusion": a.conclusion,
        "first_level_on_front": first_front, "paths": rows, "hierarchy": hierarchy,
        "not_evaluable_options": skipped, "urgency": {"status_quo_urgent_estimates": urgent,
                                                       "paths_made_infeasible": affected},
        "improving_on_status_quo": a.improving, "unresolved": a.unresolved, "infeasibility": a.certificate,
        "weights": nm.transition.model_dump(mode="json"), "epsilon": eps,
        "publication_category": category, "release_allowed": released,
        "public_layer": {"published": released and decision.released, "features": [],
                         "reason": ("catégorie " + category + " : aucune frontière nette (§75-76)") if not released
                         else decision.reason},
        "valid_as_of": {"run_created_at": ctx.manifest.created_at.isoformat(), "data_vintages": vintages},
        "output": "O = (P*, incertitude, provenance, support causal, régime normatif, options de transition)",
        "privacy_class": nm.privacy.default_access.value}
    artifacts.write_json(ctx.run_dir, "artifacts/map_r.json", product)
    record = ProvenanceRecord.create(
        "map_r.transitions", [f"validation:{content_hash(validation)}", f"transition:{tm.content_hash}"],
        [f"map_r:{content_hash(product)}"], run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    ctx.repo.record_transitions(ctx.manifest.run_id, product)
    front = sum(1 for r in rows if r["rank"] == 1)
    return {"count": len(rows), "detail": f"{concl} trajectoires={len(rows)} front={front} "
                                          f"premier_niveau={first_front} publication={'oui' if released else 'non'}"}


def _effect_of(cm: Any, lever: str | None) -> str | None:
    if lever is None:
        return None
    return next((lv.effect for lv in cm.levers if lv.lever.value == lever), None)




def _describe(step: Step) -> str:
    what = step.payload.get("lever") or step.payload.get("target")
    return f"{step.action.value} ({what})" if what else step.action.value
