"""Étapes d'un run continental (M14 ; 07 §13, 11 phase 10). Bornées, idempotentes, reprenables.

``regional_check`` → ``interfaces`` → ``regional_options`` → ``coordination`` → ``report``.

Les runs régionaux sont des runs ordinaires de la file, soumis avant le run
continental : le worker traite les runs dans l'ordre de soumission, si bien qu'un
run continental ne démarre qu'une fois ses régions terminées. Une région en échec
fait échouer la composition, avec le message de la région.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from scipy import sparse
from scipy.spatial import cKDTree
from shapely.geometry.base import BaseGeometry

from amtgo.causal.library import FrozenCausalLibrary, library_hash
from amtgo.core.provenance import ProvenanceRecord
from amtgo.db.repository import Repository
from amtgo.errors import ConfigurationError, ReproducibilityError, StageInterrupted, TopologyError
from amtgo.geo.crs import to_equal_area
from amtgo.manifests.continental import (
    ContinentalManifest,
    LayerTarget,
    check_regionals,
    mesh_pairing,
    verify_continental,
)
from amtgo.manifests.run import RunManifest, verify_manifest
from amtgo.measurement import fields as fields_mod
from amtgo.optimization import continental as cont
from amtgo.optimization.objectives import SqRelation
from amtgo.optimization.transition import ActionType, step_uncertainty, voi_indicator
from amtgo.runs import artifacts
from amtgo.runs.dfi_stages import QUADRATURE_POINTS, cached_kernel, cell_points
from amtgo.runs.map_r_stages import regional_paths
from amtgo.runs.optimizer_stages import normative_parameters
from amtgo.runs.stages import StageContext
from amtgo.runs.state import RunStatus, load_state, write_json_atomic
from amtgo.utils.canonical import content_hash


@dataclass
class ContinentalContext:
    run_dir: Path
    manifest: ContinentalManifest
    repo: Repository
    runs_root: Path
    cache_dir: Path
    should_stop: Callable[[], bool]

    def check_stop(self, what: str) -> None:
        if self.should_stop():
            raise StageInterrupted(what)

    def regional_dir(self, region_id: str) -> Path:
        rr = next(r for r in self.manifest.regions if r.region_id == region_id)
        return self.runs_root / str(rr.run_id)

    def regional(self, region_id: str) -> StageContext:
        d = self.regional_dir(region_id)
        m = RunManifest.model_validate_json((d / "manifest.json").read_text(encoding="utf-8"))
        return StageContext(d, m, self.repo, self.cache_dir, self.should_stop)

    def regionals(self) -> dict[str, StageContext]:
        return {r.region_id: self.regional(r.region_id) for r in self.manifest.regions}


def plan_steps(_: ContinentalManifest) -> list[str]:
    return ["regional_check", "interfaces", "regional_options", "coordination", "report"]


def regional_check(ctx: ContinentalContext, _: str) -> dict[str, Any]:
    verify_continental(ctx.manifest)
    out = {}
    for rr in ctx.manifest.regions:
        d = ctx.regional_dir(rr.region_id)
        if not (d / "state.json").exists():
            raise ConfigurationError(f"région {rr.region_id} : run régional {rr.run_id} absent de la file")
        st = load_state(d)
        if st.status is not RunStatus.SUCCEEDED:
            raise ConfigurationError(f"région {rr.region_id} : run régional {st.status.value} ({st.error or '-'})")
        rctx = ctx.regional(rr.region_id)
        verify_manifest(rctx.manifest)
        if rctx.manifest.manifest_hash != rr.manifest_hash:
            raise ReproducibilityError(f"région {rr.region_id} : le run régional n'est pas celui du manifeste")
        validation = artifacts.read_json(d, "artifacts/validation.json")
        map_r = artifacts.read_json(d, "artifacts/map_r.json")
        out[rr.region_id] = {
            "run_id": str(rr.run_id), "context": rr.context, "map_r_conclusion": map_r["conclusion"],
            "publication_category": validation["publication_category"], "gates": validation["gates"],
            "regime_dependent": validation["regimes"]["regime_dependent"],
            "release_allowed": validation["release_allowed"], "s_time": validation["s_time"]}
    check_regionals({rid: c.manifest for rid, c in ctx.regionals().items()})
    artifacts.write_json(ctx.run_dir, "artifacts/regions.json", {"regions": out})
    return {"count": len(out), "detail": " ".join(f"{r}={v['map_r_conclusion']}" for r, v in out.items())}


def _link_weight(kernel: sparse.csr_matrix, n: np.ndarray) -> float:
    coo = sparse.triu(kernel, k=1).tocoo()
    return float((coo.data * n[coo.row] * n[coo.col]).sum())


def _extent(ctx: StageContext, mesh_id: str) -> BaseGeometry:
    return to_equal_area(artifacts.read_mesh(ctx.run_dir, mesh_id).extent)


def interfaces(ctx: ContinentalContext, _: str) -> dict[str, Any]:
    """Totaux régionaux et liens fonctionnels qui traversent chaque interface, par paire de maillages."""
    regionals = ctx.regionals()
    pairing = mesh_pairing({r: c.manifest for r, c in regionals.items()})
    dm = next(iter(regionals.values())).manifest.dfi_model
    assert dm is not None
    length, cutoff = dm.network_kernel_length_km, dm.network_kernel_cutoff
    cross = [la for la in ctx.manifest.coordination_model.layers if la.acts_on is LayerTarget.CROSS_LINKS]
    totals: dict[str, dict[str, dict[str, float]]] = {r: {} for r in regionals}
    pts: dict[tuple[str, str], tuple[list[np.ndarray], np.ndarray]] = {}
    for pid, by_region in pairing.items():
        for rid, mesh_id in by_region.items():
            ctx.check_stop(f"interfaces {pid} {rid}")
            rctx = regionals[rid]
            mesh = artifacts.read_mesh(rctx.run_dir, mesh_id)
            pop = fields_mod.read_field(rctx.run_dir, mesh_id)[2].astype(np.float64).mean(axis=0)
            kernel = cached_kernel(rctx, mesh, length, cutoff)
            totals[rid][pid] = {"population": float(pop.sum()), "link_weight": _link_weight(kernel, pop)}
            pts[(rid, pid)] = (cell_points(mesh, QUADRATURE_POINTS), pop)
    out = []
    first_pid = next(iter(pairing))
    for a, b in combinations(sorted(regionals), 2):
        ea, eb = (_extent(regionals[r], pairing[first_pid][r]) for r in (a, b))
        overlap = ea.intersection(eb).area
        if overlap > 1e-6 * min(ea.area, eb.area):
            raise TopologyError(f"régions {a} et {b} : emprises qui se recouvrent ({overlap / 1e6:.1f} km²), "
                                "la population serait comptée deux fois")
        line = ea.boundary.intersection(eb.buffer(1.0))
        links: dict[str, dict[str, float]] = {}
        n_links = 0
        for pid in pairing:
            ctx.check_stop(f"interfaces {a}~{b} {pid}")
            (pa, na), (pb, nb) = pts[(a, pid)], pts[(b, pid)]
            ca = np.array([p.mean(axis=0) for p in pa])
            cb = np.array([p.mean(axis=0) for p in pb])
            radius = max(max(np.max(np.linalg.norm(p - p.mean(axis=0), axis=1)) for p in ps) for ps in (pa, pb))
            reach = cutoff * length + 2 * radius
            near = cKDTree(ca).query_ball_tree(cKDTree(cb), reach)
            acc: dict[str, float] = {}
            for i, js in enumerate(near):
                for j in js:
                    d = np.linalg.norm(pa[i][:, None, :] - pb[j][None, :, :], axis=2)
                    v = float(np.where(d <= cutoff * length, np.exp(-d / length), 0.0).mean())
                    if v <= 0:
                        continue
                    mid = shapely.points(*((ca[i] + cb[j]) * 500.0))  # km → m, milieu du lien
                    dist_km = float(shapely.distance(line, mid)) / 1000.0
                    sig = "+".join(sorted(la.layer_id for la in cross if la.band_km is None or dist_km <= la.band_km))
                    acc[sig] = acc.get(sig, 0.0) + v * float(na[i]) * float(nb[j])
                    n_links += 1
            links[pid] = dict(sorted(acc.items()))
        if not n_links:
            continue  # régions non adjacentes à la portée du noyau : aucune interface
        out.append({"a": a, "b": b, "border_km": float(line.length) / 1000.0, "links": links,
                    "n_links": n_links,
                    "cross_share": {pid: sum(links[pid].values()) / (sum(links[pid].values()) + sum(
                        totals[r][pid]["link_weight"] for r in (a, b))) for pid in pairing}})
    payload = {"pairing": pairing, "totals": totals, "interfaces": out,
               "kernel": {"length_km": length, "cutoff": cutoff}}
    artifacts.write_json(ctx.run_dir, "artifacts/interfaces.json", payload)
    return {"count": len(out), "detail": " ".join(
        f"{i['a']}~{i['b']} frontière={i['border_km']:.0f}km liens={i['n_links']}" for i in out) or "aucune"}


def regional_options(ctx: ContinentalContext, _: str) -> dict[str, Any]:
    """Trajectoires Map-R de chaque région, ω ré-indexés par paire de maillages, et régimes de conclusion."""
    regionals = ctx.regionals()
    pairing = mesh_pairing({r: c.manifest for r, c in regionals.items()})
    pair_of = {(rid, mesh_id): pid for pid, by in pairing.items() for rid, mesh_id in by.items()}
    out = {}
    for rid, rctx in regionals.items():
        ctx.check_stop(f"regional_options {rid}")
        rp = regional_paths(rctx)
        map_r = artifacts.read_json(rctx.run_dir, "artifacts/map_r.json")
        rows = {r["path_id"]: r for r in map_r["paths"]}
        front = {s.key for s in rp.archive.solutions if s.rank == 1}
        options = []
        for v in rp.variants:
            options.append({
                "key": v.key, "family": v.family, "top_action": rows[v.key]["top_action"], "front": v.key in front,
                "name": rows[v.key]["name"], "relation": v.relation.value,
                "relations": {k: r.value for k, r in sorted(v.relations.items())},
                "omega": [{"pair": pair_of[(rid, m)], "ontology": o,
                           "values": {k: w.get(k) for k in cont.OBJECTIVES_C}, "violations": w["violations"]}
                          for (m, o), w in sorted(v.omega.items())]})
        out[rid] = {"options": options, "eps": rp.eps,
                    "verdicts": cont.regional_verdicts(map_r["paths"], map_r["improving_on_status_quo"], rp.eps),
                    "improving": map_r["improving_on_status_quo"], "unresolved": map_r["unresolved"]}
    eps = {content_hash(v["eps"]) for v in out.values()}
    if len(eps) != 1:
        raise ConfigurationError("régions non commensurables : résolutions ε différentes")
    artifacts.write_json(ctx.run_dir, "artifacts/regional_options.json", {"regions": out})
    return {"count": sum(len(v["options"]) for v in out.values()),
            "detail": " ".join(f"{r}={sum(o['front'] for o in v['options'])}/{len(v['options'])}"
                               for r, v in out.items())}


def _options(data: dict[str, Any]) -> dict[str, list[cont.RegionOption]]:
    out = {}
    for rid, reg in data["regions"].items():
        out[rid] = [cont.RegionOption(
            rid, o["key"], o["family"], o["top_action"],
            {(w["pair"], w["ontology"]): {**w["values"], "violations": w["violations"]} for w in o["omega"]},
            SqRelation(o["relation"]), {k: SqRelation(r) for k, r in o["relations"].items()})
            for o in reg["options"]]
    return out


def _library(ctx: ContinentalContext) -> FrozenCausalLibrary:
    lib = ctx.manifest.causal_library
    effects = [d.to_effect() for d in lib.declared]
    overlap_min = ctx.regional(ctx.manifest.regions[0].region_id).manifest.normative_manifest.stability.overlap_min
    return FrozenCausalLibrary(effects, library_hash(effects), overlap_min, lib.novelty)


def coordination(ctx: ContinentalContext, _: str) -> dict[str, Any]:
    m = ctx.manifest
    cm = m.coordination_model
    first = ctx.regional(m.regions[0].region_id)
    nm, om, tm, dm = (first.manifest.normative_manifest, first.manifest.optimizer_model,
                      first.manifest.transition_model, first.manifest.dfi_model)
    assert om is not None and tm is not None and dm is not None
    regions = artifacts.read_json(ctx.run_dir, "artifacts/regions.json")["regions"]
    itf_data = artifacts.read_json(ctx.run_dir, "artifacts/interfaces.json")
    opt_data = artifacts.read_json(ctx.run_dir, "artifacts/regional_options.json")
    eps = next(iter(opt_data["regions"].values()))["eps"]
    lib = _library(ctx)

    layers, skipped = {}, {}
    iota = tm.irreversibility[ActionType.BORDER_WEAKENING]
    for la in cm.layers:
        ans = lib.query(la.effect, m.request.region)
        if not ans.known:
            skipped[la.layer_id] = f"effet {la.effect} : {ans.status} ({ans.reason})"
            continue
        iv = ans.interval()
        u = step_uncertainty(ans, dm.relative_floor)
        voi = voi_indicator(iota, ans, tm.reversible_max)
        w = nm.transition
        pen = w.lambda_irreversibility * iota + w.lambda_uncertainty * u - w.lambda_voi * voi
        layers[la.layer_id] = cont.LayerEffect(la.layer_id, la.acts_on.value,
                                               (max(0.0, iv.lo), min(1.0, iv.hi)),
                                               (la.annual_cost.lo, la.annual_cost.hi), float(pen))
    world = cont.World(
        {r: {p: cont.RegionTotals(t["population"], t["link_weight"]) for p, t in v.items()}
         for r, v in itf_data["totals"].items()},
        [cont.Interface(i["a"], i["b"], i["border_km"],
                        {p: {tuple(s.split("+")) if s else (): w for s, w in ws.items()}
                         for p, ws in i["links"].items()})
         for i in itf_data["interfaces"]],
        layers, om.border_cost_per_km)
    options = _options(opt_data)
    front = {r: {o.key for o in opts if o.key in {x["key"] for x in opt_data["regions"][r]["options"] if x["front"]}}
             for r, opts in options.items()}
    normative = normative_parameters(first)
    ctx.check_stop("coordination compose")
    comp = cont.compose(options, world, eps, nm.robustness, normative, front)
    ctx.check_stop("coordination exactness")
    comp = cont.verify_and_repair(comp, options, world, eps, nm.robustness, normative,
                                  cm.max_exhaustive_combinations)
    optimistic = cont.compose(options, world, eps, nm.robustness, normative, front, bound=cont.OPTIMISTIC)
    a = comp.archive
    front_keys = {s.key for s in a.solutions if s.rank == 1}
    exactness = [{k: v for k, v in e.items() if k != "missed_keys"} for e in comp.exactness]

    concl = cont.conclusion(a)
    sols = sorted(a.solutions, key=lambda s: (s.rank or 99, s.key))
    by_key = {c.key: c for c in comp.composites}
    names = {(r, o["key"]): o["name"] for r, reg in opt_data["regions"].items() for o in reg["options"]}

    def describe(key: str) -> dict[str, Any]:
        c = by_key[key]
        return {"regions": {r: {"path": o.key, "name": names[(r, o.key)], "top_action": o.top_action}
                            for r, o in sorted(c.options.items())},
                "layers": {i: list(ls) for i, ls in sorted(c.layers.items())}}

    rows = [{"key": s.key, "rank": s.rank, "feasible": s.feasible, "violated": s.violated,
             "status_quo": s.family == cont.SQ_FAMILY, "objectives": s.objectives, **describe(s.key)}
            for s in sols if s.rank == 1 or s.family == cont.SQ_FAMILY]
    verdicts = {r: reg["verdicts"] for r, reg in opt_data["regions"].items()}
    interface_rows = []
    for itf in world.interfaces:
        improving = comp.layer_improving.get(itf.key, [])
        robust_sets = [list(s) for s in comp.layer_fronts[itf.key] if s]
        opt_sets = [list(s) for s in optimistic.layer_fronts[itf.key] if s]
        interface_rows.append({
            "interface": itf.key, "border_km": itf.border_km,
            "border_cost": itf.border_km * om.border_cost_per_km,
            "cross_share": next(i for i in itf_data["interfaces"] if f"{i['a']}~{i['b']}" == itf.key)["cross_share"],
            "layer_front_robust": robust_sets, "layer_front_optimistic": opt_sets,
            "verdict": cont.Verdict.FRONTIERE_FONCTIONNELLE_FAIBLE.value if improving else None,
            "improving_layers": [list(s) for s in improving],
            "research_priority": [s for s in opt_sets if s not in robust_sets]})
    category = cont.worst_category(r["publication_category"] for r in regions.values())
    regime = m.constitutional_regime
    ontologies = sorted(o.ontology_id for o in first.manifest.ontology_set)
    product = {
        "conclusion": concl, "regime": regime, "publication_category": category,
        "decomposition": {"monolithic": False, "levels": ["local", "régional (Map-R)", "interfaces", "continental"],
                          "regional_fronts": {r: len(v) for r, v in comp.regional_fronts.items()},
                          "layer_fronts": {i: [list(s) for s in v] for i, v in comp.layer_fronts.items()},
                          "composed_options": len(comp.composites), "exactness": exactness,
                          "repaired": comp.repaired},
        "regions": regions, "verdicts": verdicts, "interfaces": interface_rows,
        "layers": {lid: {"mu": list(le.mu), "annual_cost": list(le.cost), "penalty": le.penalty,
                         "acts_on": le.acts_on} for lid, le in sorted(layers.items())},
        "layers_not_evaluable": skipped, "front": rows,
        "improving_on_status_quo": a.improving, "unresolved": a.unresolved, "infeasibility": a.certificate,
        "epsilon": eps, "costs_moved_to_continental_level": {
            "interface_border_management": sum(r["border_cost"] for r in interface_rows),
            "note": "coût invisible au niveau régional (frontière extérieure d'une région), compté ici"},
        "public_layer": {"published": False, "features": [],
                         "reason": f"catégorie {category} ; une composition ne produit aucune géométrie nouvelle"},
        "statement": cont.statement(regime, ontologies, lib.freeze_hash, category, len(regions)),
        "valid_as_of": {"run_created_at": m.created_at.isoformat(),
                        "regional_runs": {r: v["run_id"] for r, v in regions.items()}},
        "privacy_class": nm.privacy.default_access.value}
    artifacts.write_json(ctx.run_dir, "artifacts/continental.json", product)
    record = ProvenanceRecord.create(
        "continental.coordination",
        [f"run:{r.run_id}" for r in m.regions]
        + [f"coordination:{cm.content_hash}", f"causal_freeze:{lib.freeze_hash}"],
        [f"continental:{content_hash(product)}"], run_id=m.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_continental(m, product, [record])  # composition d'abord : la provenance s'y rattache
    checked = [e for e in exactness if e["checked"]]
    exact = "non vérifié" if not checked else "oui" if all(e["exact"] for e in checked) else "non"
    return {"count": len(rows), "detail": f"{concl} composées={len(comp.composites)} front={len(front_keys)} "
                                          f"exact={exact} catégorie={category}"}


def report(ctx: ContinentalContext, _: str) -> dict[str, Any]:
    from amtgo.runs.report import render_continental

    product = artifacts.read_json(ctx.run_dir, "artifacts/continental.json")
    write_json_atomic(ctx.run_dir / "report.md", render_continental(ctx.manifest, product))
    return {"detail": product["publication_category"]}


STAGES: dict[str, Callable[[ContinentalContext, str], dict[str, Any]]] = {
    "regional_check": regional_check, "interfaces": interfaces, "regional_options": regional_options,
    "coordination": coordination, "report": report}


def run_step(ctx: ContinentalContext, name: str) -> dict[str, Any]:
    stage, _, arg = name.partition(":")
    fn = STAGES.get(stage)
    if fn is None:
        raise ConfigurationError(f"étape continentale inconnue : {name}")
    return fn(ctx, arg)


