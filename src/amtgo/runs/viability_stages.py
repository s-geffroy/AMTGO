"""Étapes M6 : ``viability:<mesh>``, ``viability_ensemble`` et ``s2c_diagnostic``.

La viabilité des juridictions souveraines du statu quo est évaluée sous chaque
régime de la sensibilité et chaque scénario S1/S2A, sur la population **gelée**
(prompt §32). Les comptes fiscaux sont rapportés à la population du champ par
district, puis agrégés par juridiction. S2C ne produit qu'un diagnostic agrégé.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from amtgo.core.enums import EvidenceStatus, SupportType
from amtgo.core.provenance import ProvenanceRecord
from amtgo.data.ingestion import read_observations
from amtgo.errors import ConfigurationError, TopologyError
from amtgo.institutions.regimes import ConstitutionalRegime
from amtgo.institutions.status_quo import assign_cells_to_polygons
from amtgo.institutions.viability import (
    FiscalUnion,
    Territory,
    ViabilityAssessment,
    ViabilityContext,
    compute_viability,
    draw_model,
)
from amtgo.measurement import fields as fields_mod
from amtgo.runs import artifacts
from amtgo.runs.causal_stages import frozen_library
from amtgo.runs.dfi_stages import status_quo_partition
from amtgo.scenarios.model import draw_scenario
from amtgo.scenarios.projection import project_population
from amtgo.utils.canonical import content_hash

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


def regimes_evaluated(ctx: StageContext) -> list[ConstitutionalRegime]:
    """Régime du run d'abord, puis la sensibilité (sans doublon)."""
    out = [ctx.manifest.constitutional_regime]
    out += [r for r in ctx.manifest.regime_sensitivity if r.regime_id is not out[0].regime_id]
    return out


def _fiscal_draws(obs: list[Any], n: int, seed: int) -> np.ndarray:
    """(S, D) : tirages des totaux déclarés (erreur gaussienne), tronqués à 0."""
    rng = np.random.default_rng([seed, 7, len(obs)])
    mean = np.array([o.value.mean for o in obs])
    sd = np.array([o.value.std or 0.0 for o in obs])
    return np.clip(rng.normal(mean, sd, size=(n, len(obs))), 0.0, None)


def _summary(a: ViabilityAssessment) -> dict[str, Any]:
    def s(u: Any) -> dict[str, float] | None:
        return None if u is None else {"mean": u.mean, "lower": u.lower, "upper": u.upper}
    return {"status": a.status.value, "coverage": s(a.coverage), "p_shortfall": a.p_shortfall,
            "transfer_share": s(a.transfer_share), "overhead_share": s(a.overhead_share),
            "exploratory_dependency": a.exploratory_dependency, "statement": a.statement()}


def viability(ctx: StageContext, mesh_id: str) -> dict[str, Any]:
    vm = ctx.manifest.viability_model
    observed = ctx.manifest.observed_regime
    if vm is None or observed is None:
        raise ConfigurationError("aucun modèle de viabilité dans ce run")
    mesh = artifacts.read_mesh(ctx.run_dir, mesh_id)
    partition = status_quo_partition(ctx, mesh)
    level = next(lv for lv in partition.levels if lv.name == vm.level)
    fiscal = [o for o in read_observations(ctx.observations_path(vm.fiscal_source))
              if o.support_type in (SupportType.ADMIN, SupportType.POLYGON) and o.value is not None]
    revenue = sorted((o for o in fiscal if o.variable_id == vm.revenue_variable), key=lambda o: o.admin_code or "")
    cost = sorted((o for o in fiscal if o.variable_id == vm.cost_variable), key=lambda o: o.admin_code or "")
    if not revenue or [o.admin_code for o in revenue] != [o.admin_code for o in cost]:
        raise ConfigurationError(f"viabilité : recettes et coûts de {vm.fiscal_source} non appariés par district")
    fiscal_assign, _ = assign_cells_to_polygons(mesh, revenue)
    population = fields_mod.read_field(ctx.run_dir, mesh_id)[2].astype(np.float64)  # (S, N)
    n_draws, seed = population.shape[0], ctx.manifest.seeds[0]
    to_district = np.eye(len(revenue))[fiscal_assign]  # (N, D)
    pop_d = population @ to_district
    if np.any(pop_d <= 0):
        raise TopologyError(f"{mesh_id} : un district fiscal ne reçoit aucune population du champ")
    per_capita = {"revenue": _fiscal_draws(revenue, n_draws, seed) / pop_d,
                  "cost": _fiscal_draws(cost, n_draws, seed + 1) / pop_d}
    to_territory = np.eye(len(level.jurisdictions))[level.assignment]  # (N, K)
    union = FiscalUnion(
        territory_ids=list(level.jurisdictions), population=population @ to_territory,
        revenue=(population * per_capita["revenue"][:, fiscal_assign]) @ to_territory,
        service_cost=(population * per_capita["cost"][:, fiscal_assign]) @ to_territory)
    lib = frozen_library(ctx)
    region = ctx.manifest.request.region
    effects = (lib.query(vm.effects.market_access_elasticity, region),
               lib.query(vm.effects.infrastructure_cost_reduction, region))
    exploratory, overhead = draw_model(vm, effects, n_draws, seed)
    thresholds = ctx.manifest.normative_manifest.viability
    results: dict[str, Any] = {}
    guards: dict[str, Any] = {}
    for sc in ctx.manifest.scenario_set:
        if sc.diagnostic_only:
            continue
        ctx.check_stop(f"viability {mesh_id} {sc.scenario_id}")
        draws = draw_scenario(sc, n_draws, seed)
        projected = project_population(population, sc, draws)  # garde-fous §35 vérifiés à l'exécution
        guards[sc.scenario_id] = {"forced_migration": projected.forced_migration,
                                  "reform_induced_relocation": projected.reform_induced_relocation,
                                  "voluntary_response": projected.voluntary_response}
        context = ViabilityContext(union, vm, observed, thresholds, draws, effects, exploratory, overhead)
        results[sc.scenario_id] = {
            r.regime_id.value: {t: _summary(compute_viability(Territory(t, vm.level), r, sc, context))
                                for t in level.jurisdictions}
            for r in regimes_evaluated(ctx)}
    out = {"mesh_id": mesh_id, "level": vm.level, "territories": list(level.jurisdictions),
           "run_regime": ctx.manifest.constitutional_regime.regime_id.value,
           "observed_regime": observed.regime_id.value,
           "privacy_class": ctx.manifest.normative_manifest.privacy.default_access.value,
           "evidence_status": EvidenceStatus.MODEL.value, "thresholds": thresholds.model_dump(mode="json"),
           "guards": guards, "assessments": results,
           "effects": {a.effect_key: {"status": a.status, "grade": None if a.grade is None else a.grade.value,
                                      "reason": a.reason} for a in effects}}
    artifacts.write_json(ctx.run_dir, f"fields/{mesh_id}/viability.json", out)
    freeze = artifacts.read_json(ctx.run_dir, "measurement_freeze.json")
    record = ProvenanceRecord.create(
        "institutions.compute_viability",
        [f"measurement_freeze:{freeze['freeze_hash']}", f"causal_freeze:{lib.freeze_hash}",
         f"viability:{vm.content_hash}",
         f"normative:{ctx.manifest.normative_manifest_hash}"]
        + [f"scenario:{sc.content_hash}" for sc in ctx.manifest.scenario_set]
        + [f"regime:{r.content_hash}" for r in regimes_evaluated(ctx)],
        [f"viability:{mesh_id}:{content_hash(out)}"], run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    statuses = [a["status"] for by_r in results.values() for by_t in by_r.values() for a in by_t.values()]
    return {"count": len(statuses), "detail": f"viable={statuses.count('VIABLE')}/{len(statuses)}"}


def viability_ensemble(ctx: StageContext, _: str) -> dict[str, Any]:
    """S^scale de la viabilité et sensibilité au régime (05 §19)."""
    per_mesh = {d.mesh_id: artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/viability.json")
                for d in ctx.manifest.mesh_set}
    first = next(iter(per_mesh.values()))
    max_gap = 0.0
    table: dict[str, Any] = {}
    for sid, by_r in first["assessments"].items():
        for rid, by_t in by_r.items():
            for t in by_t:
                cells = [v["assessments"][sid][rid][t] for v in per_mesh.values()]
                p = [c["p_shortfall"] for c in cells]
                max_gap = max(max_gap, max(p) - min(p))
                statuses = {c["status"] for c in cells}
                entry = table.setdefault(sid, {}).setdefault(t, {})
                entry[rid] = statuses.pop() if len(statuses) == 1 else "MESH_DEPENDENT"
    regime_dependent = {sid: {t: len(set(by_r.values())) > 1 for t, by_r in by_t.items()}
                        for sid, by_t in table.items()}
    exploratory = sorted({f"{sid}|{rid}|{t}" for v in per_mesh.values() for sid, by_r in v["assessments"].items()
                          for rid, by_t in by_r.items() for t, a in by_t.items() if a["exploratory_dependency"]})
    result = {"s_scale_viability": 1.0 - max_gap, "status_by_scenario_territory_regime": table,
              "regime_dependent": regime_dependent, "exploratory_dependent": exploratory,
              "regimes": list(first["assessments"][next(iter(first["assessments"]))])}
    artifacts.write_json(ctx.run_dir, "artifacts/viability_ensemble.json", result)
    n_dep = sum(v for by_t in regime_dependent.values() for v in by_t.values())
    return {"detail": f"S_scale={result['s_scale_viability']:.2f} regime_dependent={n_dep}"}


# Sorties autorisées et interdites du diagnostic S2C (prompt §37, 06 §8) : écrites dans
# l'artefact pour que tout lecteur sache ce qui n'est délibérément pas calculé.
S2C_ALLOWED = ("aggregate_population_equivalent", "apparent_homogeneity_gain", "ratio", "confidence")
S2C_FORBIDDEN = ("groupes à déplacer", "origine/destination", "route", "calendrier", "allocation de personnes")


def s2c_diagnostic(ctx: StageContext, _: str) -> dict[str, Any]:
    """S2C sur le statu quo : NOT_APPLICABLE, son bénéfice relatif à lui-même est nul par construction.

    Le diagnostic (``scenarios.coercion``) s'appliquera aux candidats (M8–M10) ; il
    ne s'exécute jamais sans bénéfice apparent à expliquer.
    """
    out = {}
    for sc in ctx.manifest.scenario_set:
        if not sc.diagnostic_only:
            continue
        out[sc.scenario_id] = {
            "status": "NOT_APPLICABLE",
            "reason": "aucun candidat (M8) : le statu quo comparé à lui-même n'a aucun bénéfice apparent ; "
                      "K_C = 0 par construction",
            "outputs_allowed": list(S2C_ALLOWED), "outputs_forbidden": list(S2C_FORBIDDEN),
        }
    artifacts.write_json(ctx.run_dir, "artifacts/s2c_diagnostic.json", out)
    return {"count": len(out), "detail": "NOT_APPLICABLE"}
