"""Étapes M10 : ``evaluate_candidates:<mesh>`` puis ``pareto`` (archive robuste, Gate O).

Chaque candidat (M8) reçoit le gabarit institutionnel du statu quo et est évalué
sous chaque ontologie et sur chaque maillage. Une variante (famille, paramètres)
est une solution ; ses objectifs sont agrégés par ρ sur ω = (maillage, ontologie).
La contrainte de droits est dure : une violation sur un seul ω rend la variante
infaisable. Le résultat est une archive, jamais une « meilleure solution ».
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import numpy as np

from amtgo.causal.library import CausalAnswer
from amtgo.causal.model import CAUSAL_EFFECT_UNKNOWN
from amtgo.core.provenance import ProvenanceRecord
from amtgo.errors import ConfigurationError
from amtgo.geo.crs import to_equal_area
from amtgo.geo.mesh import Mesh
from amtgo.institutions.composer import Configuration, institutionalization
from amtgo.institutions.status_quo import build_institutions
from amtgo.institutions.viability import ViabilityContext, draw_model
from amtgo.measurement import fields as fields_mod
from amtgo.optimization import benchmark
from amtgo.optimization.objectives import (
    OBJECTIVES,
    UNKNOWN_OBJECTIVES,
    border_length_km,
    candidate_partition,
    evaluate_geometry,
    functional_cut,
    institutional_cost,
    transition_share,
    viability_objective,
)
from amtgo.optimization.pareto import (
    Solution,
    eps_dominates,
    infeasibility_certificate,
    nondominated_sort,
    robust,
)
from amtgo.runs import artifacts
from amtgo.runs.candidate_stages import cell_adjacency
from amtgo.runs.causal_stages import frozen_library
from amtgo.runs.dfi_stages import cached_kernel, social_state, status_quo_partition
from amtgo.runs.viability_stages import cell_accounts, viability_effects
from amtgo.scenarios.model import draw_scenario
from amtgo.utils.canonical import content_hash

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


def _edges(mesh: Mesh, adjacency: list[list[int]]) -> list[tuple[int, int, float]]:
    geoms = [to_equal_area(c.geometry) for c in mesh.cells.values()]
    return [(i, j, geoms[i].intersection(geoms[j]).length / 1000.0)
            for i, nb in enumerate(adjacency) for j in nb if j > i]


def evaluate_candidates(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    om, dm, sq_spec = ctx.manifest.optimizer_model, ctx.manifest.dfi_model, ctx.manifest.status_quo
    vm = ctx.manifest.viability_model
    if om is None or dm is None or sq_spec is None or vm is None:
        raise ConfigurationError("l'optimiseur exige D/F/I, statu quo et viabilité")
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    sq = status_quo_partition(ctx, mesh)
    regime = ctx.manifest.constitutional_regime
    cands = artifacts.read_json(ctx.run_dir, f"fields/{mesh_id}/candidates.json")["candidates"]
    arrays = dict(np.load(io.BytesIO((ctx.run_dir / "fields" / mesh_id / "candidates.npz").read_bytes())))
    kernel = cached_kernel(ctx, mesh, dm.network_kernel_length_km, dm.network_kernel_cutoff)
    population = fields_mod.read_field(ctx.run_dir, mesh_id)[2].astype(np.float64)
    pop_mean = population.mean(axis=0)
    adjacency = cell_adjacency(mesh)
    edges = _edges(mesh, adjacency)
    accounts = cell_accounts(ctx, mesh)
    n_draws, seed = population.shape[0], ctx.manifest.seeds[0]
    effects = viability_effects(ctx)
    exploratory, overhead = draw_model(vm, effects, n_draws, seed)
    scenarios = {sc.scenario_id: sc for sc in ctx.manifest.scenario_set if not sc.diagnostic_only}
    draws = {sid: draw_scenario(sc, n_draws, seed) for sid, sc in scenarios.items()}
    lib = frozen_library(ctx)
    salience = lib.query(dm.reification.effect, ctx.manifest.request.region) if dm.reification else None
    horizon = dm.reification.horizon_years if dm.reification else 10.0
    nm = ctx.manifest.normative_manifest
    weights = nm.connection_weights.as_channels()
    states = {o.ontology_id: social_state(ctx, mesh, o.ontology_id, population, kernel)[0]
              for o in ctx.manifest.ontology_set}
    sq_inst = build_institutions(sq_spec, sq)
    base_index = {o: institutionalization(st, sq, Configuration(sq_inst, [])) for o, st in states.items()}
    f_admin = float(np.mean(overhead[:, 0]))
    f_sec = float(np.mean(overhead[:, 1]))
    regime_border = sq.levels[0].border
    by_hash: dict[str, dict[str, Any]] = {}
    out = []
    for c in cands:
        ctx.check_stop(f"evaluate {mesh_id} {c['candidate_id']}")
        h = c["assignment_hash"]
        if h not in by_hash:
            assign = arrays[c["candidate_id"]]
            part = candidate_partition(assign, sq, regime_border)
            inst = build_institutions(sq_spec, part)
            union = accounts.union(assign, list(part.levels[0].jurisdictions))
            contexts = {sid: ViabilityContext(union, vm, ctx.manifest.observed_regime, nm.viability, d,  # type: ignore[arg-type]
                                              effects, exploratory, overhead) for sid, d in draws.items()}
            j_v, not_viable = viability_objective(union, regime, contexts, scenarios)
            border_km = border_length_km(edges, assign)
            per_ont = {}
            sal = salience or CausalAnswer("none", CAUSAL_EFFECT_UNKNOWN, None, None, "absent")
            for oid, st in states.items():
                per_ont[oid] = evaluate_geometry(st, part, inst, nm.rights, weights, sal, horizon, base_index[oid])
            by_hash[h] = {
                "geometry": {"J_V": j_v, "J_G": functional_cut(kernel, pop_mean, assign),
                             "J_T": transition_share(assign, sq.levels[0].assignment, pop_mean),
                             "J_inst": institutional_cost(int(assign.max()) + 1, regime, f_admin, f_sec, border_km,
                                                          om.border_cost_per_km),
                             "J_R": None},
                "not_viable_states": not_viable, "border_km": border_km, "ontologies": per_ont}
        out.append({"candidate_id": c["candidate_id"], "family": c["family"], "params": c["params"],
                    "n_states": c["n_states"], "contiguous": c["contiguous"], **by_hash[h]})
    result = {"mesh_id": mesh_id, "privacy_class": nm.privacy.default_access.value, "candidates": out,
              "institutions": "gabarit du statu quo (États ; districts découpés par les États)"}
    artifacts.write_json(ctx.run_dir, f"fields/{mesh_id}/candidate_evaluation.json", result)
    record = ProvenanceRecord.create(
        "optimization.evaluate_candidates", [f"causal_freeze:{lib.freeze_hash}", f"optimizer:{om.content_hash}"],
        [f"candidate_evaluation:{mesh_id}:{content_hash(result)}"], run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    return {"count": len(out), "detail": f"géométries distinctes={len(by_hash)}"}


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


def pareto(ctx: StageContext, _: str) -> dict[str, Any]:
    om, dm = ctx.manifest.optimizer_model, ctx.manifest.dfi_model
    assert om is not None and dm is not None
    nm = ctx.manifest.normative_manifest
    ens = artifacts.read_json(ctx.run_dir, "artifacts/candidate_ensemble.json")
    evals = {d.mesh_id: artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/candidate_evaluation.json")
             for d in ctx.manifest.mesh_set}
    sols: list[Solution] = []
    details: dict[str, Any] = {}
    for key, v in ens["variants"].items():
        omega: dict[tuple[str, str], dict[str, Any]] = {}
        violated: set[str] = set()
        contiguous = True
        for m, e in evals.items():
            c = next((x for x in e["candidates"] if f"{x['family']}|{content_hash(x['params'])}" == key), None)
            if c is None:
                continue
            contiguous &= c["contiguous"]
            for o, res in c["ontologies"].items():
                omega[(m, o)] = {**res, **c["geometry"]}
                violated |= {f"{x} (ω={m}/{o})" for x in res["violations"]}
        if not contiguous:
            violated.add("contiguïté")
        objectives: dict[str, float | None] = {}
        for k in OBJECTIVES:
            xs = [w[k] for w in omega.values() if w.get(k) is not None]
            objectives[k] = None if k in UNKNOWN_OBJECTIVES or len(xs) < len(omega) else robust(xs, nm.robustness)
        s_ont = _s_ontology(omega, dm.relative_floor)
        s_scale = v["s_scale"]
        sol = Solution(key, v["family"], v["params"], objectives, feasible=not violated, violated=sorted(violated),
                       baseline=v["family"] in ("STATUS_QUO", "NO_TERRITORIAL_CHANGE", "INSTITUTIONAL_ONLY_REFORM"))
        sols.append(sol)
        details[key] = {"n_states_by_mesh": v["n_states_by_mesh"], "s_ontology": s_ont, "s_scale": s_scale,
                        # S^time et S^parameter ne sont pas calculés : S_publish est UNKNOWN, publication bloquée.
                        "s_publish": None, "omega": len(omega)}
    eps = om.epsilon
    nondominated_sort(sols, eps)
    sq = next(s for s in sols if s.family == "STATUS_QUO")
    # Améliore-t-on le statu quo partout, hors coût de transition (Map-R : le changement a un coût) ?
    eps_wo_t = {k: x for k, x in eps.items() if k != "J_T"}
    improving = sorted(s.key for s in sols if s.feasible and not s.baseline
                       and eps_dominates(s.objectives, sq.objectives, eps_wo_t))
    certificate = infeasibility_certificate(sols, {"severe_domination_threshold": nm.rights.severe_domination_threshold,
                                                   "severe_domination_probability_max":
                                                       nm.rights.severe_domination_probability_max})
    if certificate is not None:
        conclusion = "INFEASIBLE"
    elif improving:
        conclusion = "TERRITORIAL_OPTIONS_DOMINATE_STATUS_QUO_EXCEPT_TRANSITION"
    else:
        conclusion = "NO_TERRITORIAL_CHANGE"
    bench = benchmark.run()
    gate_o = all(bench[h]["best_gap"] <= om.benchmark_tolerance for h in ("kmeans", "spectral"))
    names = {s.key: s.family + "(" + ", ".join(f"{k}={x}" for k, x in s.params.items()) + ")" for s in sols}
    archive = {
        "conclusion": conclusion, "improving_on_status_quo": [names[k] for k in improving],
        # Biais connus du vecteur d'objectifs : ils orientent l'archive et doivent accompagner toute lecture.
        "known_biases": [
            "J_R (risque) UNKNOWN : aucune donnée de conflit ou de sécurité",
            "coûts d'hétérogénéité des préférences non modélisés : J_D est le seul coût de la diversité, "
            "ce qui avantage mécaniquement les grandes unités (unions)",
            "institutions au gabarit du statu quo, non recomposées par candidat",
            "ρ = E + λ·CVaR : une valeur de ρ n'est pas une probabilité et peut dépasser 1"],
        "solutions": [{"key": s.key, "name": names[s.key], "family": s.family, "params": s.params,
                       "rank": s.rank, "feasible": s.feasible,
                       "violated": s.violated, "baseline": s.baseline, "objectives": s.objectives, **details[s.key]}
                      for s in sorted(sols, key=lambda s: (s.rank or 99, s.key))],
        "objectives": list(OBJECTIVES), "unknown_objectives": list(UNKNOWN_OBJECTIVES), "epsilon": eps,
        "robustness": nm.robustness.model_dump(mode="json"), "infeasibility": certificate,
        "benchmark": bench, "gate_o": "PASSED" if gate_o else "FAILED",
        "recommendation_status": "NOT_IDENTIFIABLE",
        "publication": "bloquée : S^time et S^parameter non calculés (S_publish UNKNOWN), effets I7, "
                       "gates M11 non passées",
        "privacy_class": nm.privacy.default_access.value}
    artifacts.write_json(ctx.run_dir, "artifacts/pareto_archive.json", archive)
    ctx.repo.record_solutions(ctx.manifest.run_id, ctx.manifest.constitutional_regime.regime_id.value, archive)
    front = sum(1 for s in sols if s.rank == 1)
    return {"count": len(sols), "detail": f"{conclusion} front={front} gate_O={archive['gate_o']}"}
