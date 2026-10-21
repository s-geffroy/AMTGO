"""Étapes M10 : ``evaluate_candidates:<mesh>`` puis ``pareto`` (archive robuste, Gate O).

Chaque candidat (M8) reçoit le gabarit institutionnel du statu quo et est évalué
sous chaque ontologie et sur chaque maillage. Une variante (famille, paramètres)
est une solution ; ses objectifs sont agrégés par ρ sur ω = (maillage, ontologie).
La contrainte de droits est dure : une violation sur un seul ω rend la variante
infaisable. Le résultat est une archive, jamais une « meilleure solution ».

M11 : un candidat qui viole la contrainte est recomposé par le composeur (J_pkg) ;
chaque évaluation garde aussi ce qu'il faut à la validation (seuils de droits
alternatifs, régimes, formes des États) ; des géométries d'attaque Goodhart sont
évaluées à part, jamais versées dans l'archive nominale.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

from amtgo.candidates.generate import is_contiguous
from amtgo.causal.library import CausalAnswer
from amtgo.causal.model import CAUSAL_EFFECT_UNKNOWN
from amtgo.core.provenance import ProvenanceRecord
from amtgo.errors import ConfigurationError
from amtgo.geo.crs import to_equal_area
from amtgo.institutions.composer import Configuration, institutionalization
from amtgo.institutions.status_quo import build_institutions
from amtgo.institutions.viability import ViabilityContext, draw_model
from amtgo.measurement import fields as fields_mod
from amtgo.optimization import benchmark
from amtgo.optimization.archive import Variant, build
from amtgo.optimization.objectives import (
    OBJECTIVES,
    UNKNOWN_OBJECTIVES,
    SqRelation,
    border_length_km,
    candidate_partition,
    evaluate_geometry,
    functional_cut,
    institutional_cost,
    objectives_for,
    sq_relation,
    transition_share,
    viability_objective,
)
from amtgo.optimization.recompose import recompose
from amtgo.runs import artifacts
from amtgo.runs.candidate_stages import cell_adjacency
from amtgo.runs.causal_stages import frozen_library
from amtgo.runs.dfi_stages import cached_kernel, social_state, status_quo_partition
from amtgo.runs.viability_stages import cell_accounts, regimes_evaluated, viability_effects
from amtgo.scenarios.model import draw_scenario
from amtgo.utils.canonical import content_hash
from amtgo.validation import goodhart

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


def _edges(geoms: list[Any], adjacency: list[list[int]]) -> list[tuple[int, int, float]]:
    return [(i, j, geoms[i].intersection(geoms[j]).length / 1000.0)
            for i, nb in enumerate(adjacency) for j in nb if j > i]


def _evaluator(ctx: StageContext, mesh_id: str) -> tuple[Callable[[np.ndarray], dict[str, Any]], dict[str, Any]]:
    """Fonction d'évaluation d'une géométrie (niveau des États) sur un maillage, et le contexte commun."""
    om, dm, sq_spec = ctx.manifest.optimizer_model, ctx.manifest.dfi_model, ctx.manifest.status_quo
    vm = ctx.manifest.viability_model
    if om is None or dm is None or sq_spec is None or vm is None:
        raise ConfigurationError("l'optimiseur exige D/F/I, statu quo et viabilité")
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    sq = status_quo_partition(ctx, mesh)
    kernel = cached_kernel(ctx, mesh, dm.network_kernel_length_km, dm.network_kernel_cutoff)
    population = fields_mod.read_field(ctx.run_dir, mesh_id)[2].astype(np.float64)
    pop_mean = population.mean(axis=0)
    adjacency = cell_adjacency(mesh)
    geoms = [to_equal_area(c.geometry) for c in mesh.cells.values()]
    edges = _edges(geoms, adjacency)
    accounts = cell_accounts(ctx, mesh)
    n_draws, seed = population.shape[0], ctx.manifest.seeds[0]
    effects = viability_effects(ctx)
    exploratory, overhead = draw_model(vm, effects, n_draws, seed)
    scenarios = {sc.scenario_id: sc for sc in ctx.manifest.scenario_set if not sc.diagnostic_only}
    draws = {sid: draw_scenario(sc, n_draws, seed) for sid, sc in scenarios.items()}
    lib = frozen_library(ctx)
    region = ctx.manifest.request.region
    salience = lib.query(dm.reification.effect, region) if dm.reification else None
    sal = salience or CausalAnswer("none", CAUSAL_EFFECT_UNKNOWN, None, None, "absent")
    horizon = dm.reification.horizon_years if dm.reification else 10.0
    cm = ctx.manifest.composer_model
    composer_effects = {k: lib.query(k, region) for k in cm.effect_keys} if cm is not None else {}
    nm = ctx.manifest.normative_manifest
    weights = nm.connection_weights.as_channels()
    states = {o.ontology_id: social_state(ctx, mesh, o.ontology_id, population, kernel)[0]
              for o in ctx.manifest.ontology_set}
    sq_inst = build_institutions(sq_spec, sq)
    base_index = {o: institutionalization(st, sq, Configuration(sq_inst, [])) for o, st in states.items()}
    f_admin = float(np.mean(overhead[:, 0]))
    f_sec = float(np.mean(overhead[:, 1]))
    regime_border = sq.levels[0].border
    regimes = regimes_evaluated(ctx)
    nominal = ctx.manifest.constitutional_regime.regime_id.value
    alt_tau = om.sensitivity.severe_domination_threshold
    sq_top = sq.levels[0].assignment

    def evaluate(assign: np.ndarray) -> dict[str, Any]:
        part = candidate_partition(assign, sq, regime_border)
        inst = build_institutions(sq_spec, part)
        union = accounts.union(assign, list(part.levels[0].jurisdictions))
        contexts = {sid: ViabilityContext(union, vm, ctx.manifest.observed_regime, nm.viability, d,  # type: ignore[arg-type]
                                          effects, exploratory, overhead) for sid, d in draws.items()}
        border_km = border_length_km(edges, assign)
        n_states = int(assign.max()) + 1
        by_regime = {}
        for r in regimes:
            j_v, not_viable = viability_objective(union, r, contexts, scenarios)
            by_regime[r.regime_id.value] = {
                "J_V": j_v, "not_viable_states": not_viable,
                "J_inst": institutional_cost(n_states, r, f_admin, f_sec, border_km, om.border_cost_per_km)}
        per_ont = {}
        for oid, st in states.items():
            res = evaluate_geometry(st, part, inst, nm.rights, weights, sal, horizon, base_index[oid],
                                    alt_thresholds=alt_tau)
            package, j_pkg = None, 0.0
            if res["violations"] and cm is not None:
                # M11 : chercher un paquet à géométrie fixe avant de déclarer la géométrie infaisable.
                rc = recompose(st, part, inst, nm.rights, weights, cm, composer_effects, adjacency, ctx.check_stop)
                package = rc.as_json()
                if rc.configuration is not None:
                    res = evaluate_geometry(st, part, rc.configuration.institutions, nm.rights, weights, sal,
                                            horizon, base_index[oid], rc.configuration.overlays, alt_tau)
                    j_pkg = rc.cost
            per_ont[oid] = {**res, "J_pkg": j_pkg, "package": package}
        return {
            "geometry": {"J_V": by_regime[nominal]["J_V"], "J_G": functional_cut(kernel, pop_mean, assign),
                         "J_T": transition_share(assign, sq_top, pop_mean),
                         "J_inst": by_regime[nominal]["J_inst"], "J_R": None, "J_P": None},
            "by_regime": by_regime, "not_viable_states": by_regime[nominal]["not_viable_states"],
            "border_km": border_km, "sq_relation": sq_relation(assign, sq_top).value,
            "shapes": goodhart.state_shapes(geoms, assign, pop_mean, adjacency), "ontologies": per_ont}

    common = {"sq_top": sq_top, "adjacency": adjacency, "pop_mean": pop_mean, "f_admin": f_admin, "f_sec": f_sec,
              "freeze_hash": lib.freeze_hash, "channels": {
                  "integration": sorted(c.value for st in states.values() for c in st.exposure),
                  "fragmentation": sorted({c.value for st in states.values() for c in st.ties}
                                          | {c.value for st in states.values() for c, _ in st.group_ties}),
                  "national_identity": any(st.national_identity is not None for st in states.values())}}
    return evaluate, common


def evaluate_candidates(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    om = ctx.manifest.optimizer_model
    assert om is not None
    evaluate, common = _evaluator(ctx, mesh_id)
    cands = artifacts.read_json(ctx.run_dir, f"fields/{mesh_id}/candidates.json")["candidates"]
    arrays = dict(np.load(io.BytesIO((ctx.run_dir / "fields" / mesh_id / "candidates.npz").read_bytes())))
    by_hash: dict[str, dict[str, Any]] = {}
    out = []
    for c in cands:
        ctx.check_stop(f"evaluate {mesh_id} {c['candidate_id']}")
        h = c["assignment_hash"]
        if h not in by_hash:
            by_hash[h] = evaluate(arrays[c["candidate_id"]])
        out.append({"candidate_id": c["candidate_id"], "family": c["family"], "params": c["params"],
                    "n_states": c["n_states"], "contiguous": c["contiguous"], **by_hash[h]})
    # Attaques Goodhart (05 §14) : évaluées comme des candidats, jamais versées dans l'archive nominale.
    attacks = []
    for name, assign in goodhart.attacks(common["sq_top"], common["adjacency"], common["pop_mean"]).items():
        ctx.check_stop(f"evaluate {mesh_id} {name}")
        attacks.append({"candidate_id": name, "family": name, "params": {}, "n_states": int(assign.max()) + 1,
                        "contiguous": is_contiguous(assign, common["adjacency"]), **evaluate(assign)})
    nm = ctx.manifest.normative_manifest
    result = {"mesh_id": mesh_id, "privacy_class": nm.privacy.default_access.value, "candidates": out,
              "attacks": attacks, "f_admin": common["f_admin"], "f_sec": common["f_sec"],
              "channels": common["channels"],
              "institutions": "gabarit du statu quo (États ; districts découpés par les États), "
                              "recomposé par le composeur si la contrainte de droits est violée"}
    artifacts.write_json(ctx.run_dir, f"fields/{mesh_id}/candidate_evaluation.json", result)
    record = ProvenanceRecord.create(
        "optimization.evaluate_candidates",
        [f"causal_freeze:{common['freeze_hash']}", f"optimizer:{om.content_hash}"],
        [f"candidate_evaluation:{mesh_id}:{content_hash(result)}"], run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    recomposed = sum(1 for v in by_hash.values() for o in v["ontologies"].values() if o["package"] is not None)
    return {"count": len(out), "detail": f"géométries distinctes={len(by_hash)} recomposées={recomposed} "
                                         f"attaques={len(attacks)}"}


def _s_ontology(by_omega: dict[tuple[str, str], dict[str, Any]], floor: float) -> float:
    """1 − écart relatif maximal des objectifs dépendant de l'ontologie, entre ontologies, par maillage."""
    meshes = sorted({m for m, _ in by_omega})
    gaps = [0.0]
    for m in meshes:
        vals = [v for (mm, _), v in by_omega.items() if mm == m]
        for k in ("J_D", "J_F", "J_conn", "J_reif"):
            xs = [v[k] for v in vals if v.get(k) is not None]
            if len(xs) > 1:
                hi, lo = max(xs), min(xs)
                gaps.append((hi - lo) / max(abs(hi), abs(lo), floor))
    return 1.0 - max(gaps)


def _variant(key: str, family: str, params: dict[str, Any], rows: dict[str, dict[str, Any]]) -> Variant:
    """Variante à partir de ses évaluations par maillage (une ligne par maillage)."""
    omega: dict[tuple[str, str], dict[str, Any]] = {}
    contiguous = True
    relations = set()
    for m, c in rows.items():
        contiguous &= c["contiguous"]
        relations.add(c["sq_relation"])
        for o, res in c["ontologies"].items():
            omega[(m, o)] = {**res, **c["geometry"], "_mesh": m, "_by_regime": c["by_regime"],
                             "_border_km": c["border_km"]}
    # Relation au statu quo : la même sur tous les maillages, sinon indéterminée.
    relation = SqRelation(relations.pop()) if len(relations) == 1 else SqRelation.CROSSING
    return Variant(key, family, params, omega, contiguous, relation)


def variants(ctx: StageContext) -> tuple[list[Variant], list[Variant], dict[str, dict[str, Any]]]:
    """Variantes de l'ensemble M8 et attaques Goodhart, avec leurs évaluations sur chaque maillage."""
    ens = artifacts.read_json(ctx.run_dir, "artifacts/candidate_ensemble.json")
    evals = {d.mesh_id: artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/candidate_evaluation.json")
             for d in ctx.manifest.mesh_set}
    out = []
    rows_by_key = {}
    for key, v in ens["variants"].items():
        rows = {m: c for m, e in evals.items() for c in e["candidates"]
                if f"{c['family']}|{content_hash(c['params'])}" == key}
        rows_by_key[key] = rows
        out.append(_variant(key, v["family"], v["params"], rows))
    # Relations d'emboîtement par paire (M13) : la même sur tous les maillages, sinon indéterminée.
    found: dict[tuple[str, str], set[str]] = {}
    for m in evals:
        arrays = dict(np.load(io.BytesIO((ctx.run_dir / "fields" / m / "candidates.npz").read_bytes())))
        assign = {k: arrays[r[m]["candidate_id"]] for k, r in rows_by_key.items() if m in r}
        for a, xa in assign.items():
            for b, xb in assign.items():
                if a != b:
                    found.setdefault((a, b), set()).add(sq_relation(xa, xb).value)
    for v in out:
        v.relations.update({b: SqRelation(r.pop()) if len(r) == 1 else SqRelation.CROSSING
                            for (a, b), r in found.items() if a == v.key})
    names = sorted({a["family"] for e in evals.values() for a in e["attacks"]})
    attacks = [_variant(n, n, {}, {m: a for m, e in evals.items() for a in e["attacks"] if a["family"] == n})
               for n in names]
    return out, attacks, evals


def mode_objectives(ctx: StageContext) -> tuple[str, ...]:
    """Objectifs du mode de carte du run (Map-R : avec transition ; Map-C-Shallow : sans, 02 §21)."""
    return objectives_for(ctx.manifest.request.map_mode.value)


def normative_parameters(ctx: StageContext) -> dict[str, Any]:
    r = ctx.manifest.normative_manifest.rights
    return {"severe_domination_threshold": r.severe_domination_threshold,
            "severe_domination_probability_max": r.severe_domination_probability_max}


def pareto(ctx: StageContext, _: str) -> dict[str, Any]:
    om, dm = ctx.manifest.optimizer_model, ctx.manifest.dfi_model
    assert om is not None and dm is not None
    nm = ctx.manifest.normative_manifest
    ens = artifacts.read_json(ctx.run_dir, "artifacts/candidate_ensemble.json")
    vs, _attacks, _evals = variants(ctx)
    objectives = mode_objectives(ctx)
    arch = build(vs, om.epsilon, nm.robustness, normative_parameters(ctx), objectives)
    details = {}
    for v in vs:
        packages = sorted({w["package"]["option"] or w["package"]["conclusion"]
                           for w in v.omega.values() if w.get("package")})
        details[v.key] = {"n_states_by_mesh": ens["variants"][v.key]["n_states_by_mesh"],
                          "s_ontology": _s_ontology(v.omega, dm.relative_floor),
                          "s_scale": ens["variants"][v.key]["s_scale"],
                          # S^time et S^parameter : étape ``validation`` (M11) ; S_publish y est calculé.
                          "s_publish": None, "omega": len(v.omega), "sq_relation": v.relation.value,
                          "institutional_packages": packages}
    bench = benchmark.run()
    gate_o = all(bench[h]["best_gap"] <= om.benchmark_tolerance for h in ("kmeans", "spectral"))
    names = {s.key: s.family + "(" + ", ".join(f"{k}={x}" for k, x in s.params.items()) + ")"
             for s in arch.solutions}
    archive = {
        "conclusion": arch.conclusion, "improving_on_status_quo": [names[k] for k in arch.improving],
        # Dominent le statu quo sur les objectifs connus ; un objectif inconnu peut renverser la dominance.
        "unresolved_dominance": {names[k]: b for k, b in arch.unresolved.items()},
        # Biais connus du vecteur d'objectifs : ils orientent l'archive et doivent accompagner toute lecture.
        "known_biases": [
            "J_R (risque) UNKNOWN : aucune donnée de conflit ou de sécurité",
            "J_P (hétérogénéité des préférences) UNKNOWN : aucune enquête de préférences ; seul l'axiome "
            "de monotonie par fusion est utilisé, et seulement pour refuser une conclusion",
            "recomposition institutionnelle limitée aux leviers à géométrie fixe du composeur M9, et "
            "seulement pour lever une violation de droits",
            "ρ = E + λ·CVaR : une valeur de ρ n'est pas une probabilité et peut dépasser 1"],
        "solutions": [{"key": s.key, "name": names[s.key], "family": s.family, "params": s.params,
                       "rank": s.rank, "feasible": s.feasible,
                       "violated": s.violated, "baseline": s.baseline, "objectives": s.objectives, **details[s.key]}
                      for s in sorted(arch.solutions, key=lambda s: (s.rank or 99, s.key))],
        "objectives": list(objectives), "unknown_objectives": list(UNKNOWN_OBJECTIVES), "epsilon": om.epsilon,
        "map_mode": ctx.manifest.request.map_mode.value,
        "legacy_objectives_removed": [k for k in OBJECTIVES if k not in objectives],
        "robustness": nm.robustness.model_dump(mode="json"), "infeasibility": arch.certificate,
        "benchmark": bench, "gate_o": "PASSED" if gate_o else "FAILED",
        "recommendation_status": "NOT_IDENTIFIABLE",
        "publication": "décidée par l'étape validation (gates M, C, O, S, R ; S_publish)",
        "privacy_class": nm.privacy.default_access.value}
    artifacts.write_json(ctx.run_dir, "artifacts/pareto_archive.json", archive)
    ctx.repo.record_solutions(ctx.manifest.run_id, ctx.manifest.constitutional_regime.regime_id.value, archive)
    return {"count": len(arch.solutions),
            "detail": f"{arch.conclusion} front={len(arch.front)} gate_O={archive['gate_o']}"}
