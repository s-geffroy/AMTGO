"""Étape M11 ``validation`` : stabilité, ablations, Goodhart, falsification, confidentialité, gates.

Après l'archive (``pareto``), on recalcule la même archive sous :

- chaque valeur alternative d'un paramètre normatif, un à la fois (05 §18) →
  S^parameter par variante ; un paramètre qui change la conclusion est un
  **choix politique**, pas une conclusion scientifique ;
- chaque régime constitutionnel de la sensibilité (05 §19 ; J_V et J_inst) ;
- chaque maillage seul (05 §5, prompt §45 : un changement majeur ne doit pas
  dépendre d'une seule résolution) ;
- l'ablation de chaque module (05 §13) ;
- l'ajout des attaques Goodhart (05 §14) : une attaque au front sans signalement
  est une faille.

S'y ajoutent les contrôles de falsification (05 §11), le red-team de
confidentialité (05 §15-16) et les gates M, C, O, S, R (05 §20). S^time exige au
moins deux millésimes de données : sinon il est UNKNOWN, et S^publish avec lui.
La catégorie de publication (05 §21) en découle ; rien n'est publié hors
ROBUST/CONDITIONAL avec tous les gates passés.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from amtgo.core.enums import ComputabilityClass, PrivacyClass
from amtgo.core.provenance import ProvenanceRecord
from amtgo.manifests.normative import RobustnessWeights
from amtgo.measurement import fields as fields_mod
from amtgo.optimization.archive import Archive, Variant, build
from amtgo.optimization.objectives import OBJECTIVES
from amtgo.privacy.guard import ExportLayer
from amtgo.privacy.redteam import gate_s
from amtgo.runs import artifacts
from amtgo.runs.optimizer_stages import normative_parameters, variants
from amtgo.runs.viability_stages import regimes_evaluated
from amtgo.utils.canonical import content_hash
from amtgo.validation import falsification, goodhart
from amtgo.validation.stability import agreement, publication_category, release_allowed, s_publish

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext

Transform = Callable[[tuple[str, str], dict[str, Any]], dict[str, Any]]


def _rights_feasibility(eps_max: float, key: str | None = None) -> Transform:
    """Faisabilité relue sur J_D (P(D > τ) ≤ ε), à configuration institutionnelle fixée au nominal."""
    def fn(_: tuple[str, str], w: dict[str, Any]) -> dict[str, Any]:
        j_d = w["J_D"] if key is None else w["J_D_by_threshold"][key]
        return {**w, "J_D": j_d, "violations": [] if j_d <= eps_max else [f"droits:P(D>τ)={j_d:.3f}>ε"]}
    return fn


def _border_cost(delta: float) -> Transform:
    def fn(_: tuple[str, str], w: dict[str, Any]) -> dict[str, Any]:
        return {**w, "J_inst": w["J_inst"] + w["_border_km"] * delta}
    return fn


def _regime(regime_id: str) -> Transform:
    def fn(_: tuple[str, str], w: dict[str, Any]) -> dict[str, Any]:
        r = w["_by_regime"][regime_id]
        return {**w, "J_V": r["J_V"], "J_inst": r["J_inst"]}
    return fn


def _on_mesh(mesh_id: str) -> Callable[[tuple[str, str]], bool]:
    return lambda omega: omega[0] == mesh_id


def _no_rights(_: tuple[str, str], w: dict[str, Any]) -> dict[str, Any]:
    return {**w, "violations": []}


def _sensitivity(ctx: StageContext, vs: list[Variant], nominal: Archive) -> dict[str, Any]:
    om = ctx.manifest.optimizer_model
    assert om is not None
    nm = ctx.manifest.normative_manifest
    norm = normative_parameters(ctx)
    eps_max = nm.rights.severe_domination_probability_max
    sp = om.sensitivity
    settings: list[tuple[str, Any, list[Variant], dict[str, float], RobustnessWeights]] = []
    for tau in sp.severe_domination_threshold:
        settings.append(("severe_domination_threshold", tau,
                         [v.with_omega(_rights_feasibility(eps_max, repr(tau))) for v in vs], om.epsilon,
                         nm.robustness))
    for e in sp.severe_domination_probability_max:
        settings.append(("severe_domination_probability_max", e,
                         [v.with_omega(_rights_feasibility(e)) for v in vs], om.epsilon, nm.robustness))
    for r in sp.robustness:
        settings.append(("robustness", r.model_dump(mode="json"), vs, om.epsilon, r))
    for f in sp.epsilon_scale:
        settings.append(("epsilon_scale", f, vs, {k: x * f for k, x in om.epsilon.items()}, nm.robustness))
    for c in sp.border_cost_per_km:
        delta = c - om.border_cost_per_km
        settings.append(("border_cost_per_km", c, [v.with_omega(_border_cost(delta)) for v in vs], om.epsilon,
                         nm.robustness))
    rows, statuses = [], []
    for name, value, svs, eps, rob in settings:
        ctx.check_stop(f"validation sensibilité {name}")
        a = build(svs, eps, rob, norm)
        statuses.append(a.status)
        rows.append({"parameter": name, "value": value, "conclusion": a.conclusion, "front": a.front,
                     "entered_front": sorted(set(a.front) - set(nominal.front)),
                     "left_front": sorted(set(nominal.front) - set(a.front)),
                     "conclusion_changed": a.conclusion != nominal.conclusion})
    political = sorted({r["parameter"] for r in rows if r["conclusion_changed"]})
    return {"settings": rows, "s_parameter": agreement(nominal.status, statuses), "political_choices": political}


def _regimes(ctx: StageContext, vs: list[Variant], nominal: Archive) -> dict[str, Any]:
    om = ctx.manifest.optimizer_model
    assert om is not None
    nm = ctx.manifest.normative_manifest
    out = {}
    for r in regimes_evaluated(ctx)[1:]:
        rid = r.regime_id.value
        rvs = [v.with_omega(_regime(rid)) for v in vs]
        a = build(rvs, om.epsilon, nm.robustness, normative_parameters(ctx))
        out[rid] = {"conclusion": a.conclusion, "front": a.front,
                    "conclusion_changed": a.conclusion != nominal.conclusion}
    return {"nominal": ctx.manifest.constitutional_regime.regime_id.value, "alternatives": out,
            "scope": "J_V et J_inst recalculés par régime ; frontières σ et domination au régime du run",
            "regime_dependent": any(x["conclusion_changed"] for x in out.values())}


def multiscale(vs: list[Variant], meshes: list[str], eps: dict[str, float], robustness: RobustnessWeights,
               normative: dict[str, Any]) -> dict[str, Any]:
    """Archive par maillage seul : une variante au front d'un seul maillage dépend d'une résolution (§45)."""
    per_mesh = {}
    for m in meshes:
        a = build([v.restricted(_on_mesh(m)) for v in vs], eps, robustness, normative)
        per_mesh[m] = {"conclusion": a.conclusion, "front": a.front}
    on_front = {v.key: sorted(m for m in meshes if v.key in per_mesh[m]["front"]) for v in vs}
    baseline = {v.key for v in vs if v.baseline}
    single = sorted(k for k, ms in on_front.items() if len(meshes) > 1 and len(ms) == 1 and k not in baseline)
    dependent = sorted(k for k, ms in on_front.items() if 0 < len(ms) < len(meshes))
    return {"per_mesh": per_mesh, "front_meshes": on_front, "single_mesh_dependent": single,
            "mesh_dependent": dependent,
            "conclusion_stable": len({x["conclusion"] for x in per_mesh.values()}) == 1}


def _ablations(ctx: StageContext, vs: list[Variant], nominal: Archive,
               channels: dict[str, Any]) -> list[dict[str, Any]]:
    om = ctx.manifest.optimizer_model
    assert om is not None
    nm = ctx.manifest.normative_manifest
    norm = normative_parameters(ctx)

    def drop(*ks: str) -> tuple[str, ...]:
        return tuple(k for k in OBJECTIVES if k not in ks)

    plain = RobustnessWeights(cvar_alpha=nm.robustness.cvar_alpha, lambda_tail=0.0, lambda_var=0.0)
    cases: list[tuple[str, str, list[Variant], tuple[str, ...], RobustnessWeights]] = [
        ("D", "J_D et contrainte de droits retirés", [v.with_omega(_no_rights) for v in vs], drop("J_D"),
         nm.robustness),
        ("F", "J_F retiré", vs, drop("J_F"), nm.robustness),
        ("I", "J_conn retiré", vs, drop("J_conn"), nm.robustness),
        ("uncertainty", "ρ = E (sans queue ni variance)", vs, OBJECTIVES, plain),
        ("causal_layer", "objectifs dépendant de la bibliothèque gelée retirés (J_V, J_pkg, J_reif)", vs,
         drop("J_V", "J_pkg", "J_reif"), nm.robustness),
        ("reification", "J_reif retiré", vs, drop("J_reif"), nm.robustness),
    ]
    out = []
    for name, what, avs, objs, rob in cases:
        ctx.check_stop(f"validation ablation {name}")
        a = build(avs, om.epsilon, rob, norm, objs)
        out.append({"ablation": name, "status": "RUN", "what": what, "conclusion": a.conclusion,
                    "conclusion_changed": a.conclusion != nominal.conclusion,
                    "entered_front": sorted(set(a.front) - set(nominal.front)),
                    "left_front": sorted(set(nominal.front) - set(a.front)),
                    "feasible": sum(1 for s in a.solutions if s.feasible)})
    absent = {
        "national_identity": (not channels["national_identity"] and "identity" not in channels["integration"],
                              "aucune identité nationale ni canal identitaire dans ce run"),
        "mobility": ("mobility" not in channels["fragmentation"], "aucun canal de mobilité dans ce run"),
        "potential_infrastructure": (True, "aucun module d'infrastructure potentielle dans J"),
    }
    for name, (is_absent, why) in absent.items():
        out.append({"ablation": name, "status": "NOT_APPLICABLE" if is_absent else "NOT_RUN",
                    "what": why if is_absent else "exige une réévaluation des géométries (non faite)"})
    return out


def _goodhart(ctx: StageContext, vs: list[Variant], attacks: list[Variant],
              evals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    om = ctx.manifest.optimizer_model
    assert om is not None and om.goodhart is not None
    nm = ctx.manifest.normative_manifest
    a = build(vs + attacks, om.epsilon, nm.robustness, normative_parameters(ctx))
    shapes: dict[str, list[dict[str, float]]] = {}
    for e in evals.values():
        for c in [*e["candidates"], *e["attacks"]]:
            key = c["family"] if c["family"].startswith(goodhart.ATTACK_PREFIX) else \
                f"{c['family']}|{content_hash(c['params'])}"
            shapes.setdefault(key, []).append(c["shapes"])
    # Pire cas sur les maillages : un signalement sur un seul maillage suffit.
    worst = {k: {f: (max if f == "border_protrusion_share" else min)(s[f] for s in xs) for f in xs[0]}
             for k, xs in shapes.items()}
    flagged = {k: goodhart.flags(s, om.goodhart) for k, s in worst.items()}
    sq = next(s for s in a.solutions if s.family == "STATUS_QUO")
    rows = []
    for s in a.solutions:
        if not s.family.startswith(goodhart.ATTACK_PREFIX):
            continue
        on_front = s.rank == 1
        rows.append({"attack": s.family, "feasible": s.feasible, "rank": s.rank, "on_front": on_front,
                     "flags": flagged.get(s.key, []), "violated": s.violated,
                     "reduces_J_D": None if s.objectives["J_D"] is None or sq.objectives["J_D"] is None
                     else s.objectives["J_D"] < sq.objectives["J_D"],
                     "loophole": on_front and not flagged.get(s.key)})
    return {"attacks": rows, "flagged_variants": {k: f for k, f in flagged.items()
                                                  if f and not k.startswith(goodhart.ATTACK_PREFIX)},
            "thresholds": om.goodhart.model_dump(mode="json"),
            "status": "FAILED" if any(r["loophole"] for r in rows) else "PASSED",
            "regression_tests": "tests/redteam/test_m11_redteam.py"}


def _gate_m(ctx: StageContext) -> tuple[str, ComputabilityClass, dict[str, Any]]:
    classes, calib = [], {}
    for d in ctx.manifest.mesh_set:
        meta = fields_mod.read_field(ctx.run_dir, d.mesh_id)[0]
        classes.append(ComputabilityClass(meta["computability"]))
        val = artifacts.read_json(ctx.run_dir, f"fields/{d.mesh_id}/validation.json")["calibration"]
        calib[d.mesh_id] = val.get("total_covered") if val.get("status") == "done" else None
    worst = min(classes, key=lambda c: "DCBA".index(c.value))
    ok = worst in (ComputabilityClass.A, ComputabilityClass.B) and all(v is not False for v in calib.values())
    return ("PASSED" if ok else "FAILED"), worst, {"computability": worst.value, "calibration_total_covered": calib}


def _inventory(ctx: StageContext) -> list[ExportLayer]:
    """Couches que ce run produit, telles qu'elles sortiraient (aucune n'est exportée ici)."""
    nm = ctx.manifest.normative_manifest
    cls = nm.privacy.default_access
    layers = [ExportLayer(f"mesh_{d.mesh_id}", PrivacyClass.PUBLIC, False, False, False, 0, ("geometry",), d.mesh_id)
              for d in ctx.manifest.mesh_set]
    for d in ctx.manifest.mesh_set:
        samples = fields_mod.read_field(ctx.run_dir, d.mesh_id)[2]
        mean = samples.mean(axis=0)
        positive = mean[mean > 0]
        layers.append(ExportLayer(f"population_{d.mesh_id}", cls, True, False, False, int(mean.size),
                                  ("population",), d.mesh_id, float(positive.min()) if positive.size else None))
        layers.append(ExportLayer(f"composition_{d.mesh_id}", cls, True, True, False, int(mean.size),
                                  ("group_share",), d.mesh_id))
        layers.append(ExportLayer(f"dfi_{d.mesh_id}", cls, True, True, False, 0, ("group_share",), d.mesh_id))
        layers.append(ExportLayer(f"candidates_{d.mesh_id}", cls, False, False, False, 0, ("boundary",), d.mesh_id,
                                  derived_from_group_attributes=True))
    layers.append(ExportLayer("pareto_archive", cls, False, False, False, 0, ("objectives",), "archive",
                              derived_from_group_attributes=True))
    return layers


def validation(ctx: StageContext, _: str) -> dict[str, Any]:
    om = ctx.manifest.optimizer_model
    assert om is not None
    nm = ctx.manifest.normative_manifest
    archive = artifacts.read_json(ctx.run_dir, "artifacts/pareto_archive.json")
    vs, attacks, evals = variants(ctx)
    nominal = build(vs, om.epsilon, nm.robustness, normative_parameters(ctx))
    channels = next(iter(evals.values()))["channels"]
    sens = _sensitivity(ctx, vs, nominal)
    regimes = _regimes(ctx, vs, nominal)
    ms = multiscale(vs, [d.mesh_id for d in ctx.manifest.mesh_set], om.epsilon, nm.robustness,
                    normative_parameters(ctx))
    ablations = _ablations(ctx, vs, nominal, channels)
    gh: dict[str, Any] = (_goodhart(ctx, vs, attacks, evals) if om.goodhart is not None
                          else {"status": "NOT_RUN", "attacks": []})
    # Variantes du front nominal signalées : revue humaine requise avant toute publication (01 §17).
    gh["front_flagged_variants"] = {k: f for k, f in gh.get("flagged_variants", {}).items() if k in nominal.front}
    ctx.check_stop("validation falsification")
    falsif = falsification.run_controls()
    privacy = gate_s(_inventory(ctx), nm.privacy)
    # S^time : au moins deux millésimes des sources de mesure de population.
    vintages = {s.manifest.temporal_start for s in ctx.manifest.data_manifest
                if "population_measurement" in s.use.roles}
    by_key = {s["key"]: s for s in archive["solutions"]}
    stability = {}
    for v in vs:
        comps = {"s_ontology": by_key[v.key]["s_ontology"], "s_scale": by_key[v.key]["s_scale"],
                 "s_time": None, "s_parameter": sens["s_parameter"].get(v.key)}
        stability[v.key] = {**comps, "s_publish": s_publish(comps)}
    s_time_note = (f"UNKNOWN : un seul millésime de données ({sorted(map(str, vintages))})" if len(vintages) < 2
                   else "UNKNOWN : comparaison entre millésimes non implémentée (M12+)")
    gate_m, computability, gate_m_detail = _gate_m(ctx)
    causal = artifacts.read_json(ctx.run_dir, "artifacts/causal_validation.json") \
        if ctx.manifest.causal_library is not None else None
    falsif_ok = all(c["status"] != "FAILED" for c in falsif)
    gate_o = "PASSED" if archive["gate_o"] == "PASSED" and gh["status"] == "PASSED" else "FAILED"
    # S^publish de l'option qui changerait la carte : la pire des variantes non baselines au front.
    front_changes = [k for k in nominal.front if not next(v for v in vs if v.key == k).baseline]
    pubs = [stability[k]["s_publish"] for k in front_changes]
    s_pub = None if not pubs or any(p is None for p in pubs) else min(p for p in pubs if p is not None)
    tau = nm.stability.publish_min
    gate_r = ("NOT_EVALUABLE" if s_pub is None else
              "PASSED" if s_pub >= tau and not ms["single_mesh_dependent"] and falsif_ok
              and not gh.get("front_flagged_variants") else "FAILED")
    gates = {"M": gate_m, "C": "NOT_APPLICABLE" if causal is None else causal["gate_c"], "O": gate_o,
             "S": privacy["gate_s"], "R": gate_r}
    applicable = {k: g for k, g in gates.items() if g != "NOT_APPLICABLE"}
    category = publication_category(applicable, s_pub, tau, computability, nominal.conclusion,
                                    bool(sens["political_choices"]), regimes["regime_dependent"])
    released = release_allowed(category, applicable)
    result = {
        "conclusion": nominal.conclusion, "gates": gates, "publication_category": category.value,
        "names": {s["key"]: s["name"] for s in archive["solutions"]},
        "release_allowed": released, "s_publish": s_pub, "s_publish_tau": tau, "s_time": s_time_note,
        "stability": stability, "sensitivity": sens, "regimes": regimes, "multiscale": ms,
        "ablations": ablations, "goodhart": gh, "falsification": falsif, "privacy": privacy,
        "gate_m": gate_m_detail,
        "release_note": "aucune carte territoriale publiée" if not released else "publication permise",
        "privacy_class": nm.privacy.default_access.value}
    artifacts.write_json(ctx.run_dir, "artifacts/validation.json", result)
    record = ProvenanceRecord.create(
        "validation.release_gates", [f"pareto_archive:{content_hash(archive)}"],
        [f"validation:{content_hash(result)}"], run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    ctx.repo.record_validation(ctx.manifest.run_id, result)
    summary = " ".join(f"{k}={v}" for k, v in gates.items())
    return {"detail": f"{category.value} {summary} release={'oui' if released else 'non'}"}


