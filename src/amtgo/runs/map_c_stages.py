"""Étape M13 ``map_c`` : produit Map-C-Shallow (02 §21, 01 §6, 11 phase 9).

L'archive et la validation du run ont déjà été calculées sans J_T (mode
C_SHALLOW). On y ajoute : le rang de la géométrie actuelle sans privilège, la
prime de l'existant (comparaison avec l'archive Map-R sur les mêmes
évaluations), l'inventaire hybride de ce qui est conservé de X_2026, le gate de
phase 9 et la formulation conditionnelle. Aucune géométrie n'est exportée.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from amtgo.core.provenance import ProvenanceRecord
from amtgo.errors import ConfigurationError
from amtgo.optimization.archive import build
from amtgo.optimization.counterfactual import HYBRID_KEPT, REMOVED, legacy_premium, phase_gate, statement
from amtgo.optimization.objectives import objectives_for
from amtgo.runs import artifacts
from amtgo.runs.causal_stages import frozen_library
from amtgo.runs.optimizer_stages import normative_parameters, variants
from amtgo.utils.canonical import content_hash

if TYPE_CHECKING:
    from amtgo.runs.stages import StageContext


def map_c(ctx: StageContext, _: str) -> dict[str, Any]:
    om = ctx.manifest.optimizer_model
    if om is None:
        raise ConfigurationError("Map-C-Shallow exige l'archive de Pareto")
    nm = ctx.manifest.normative_manifest
    archive = artifacts.read_json(ctx.run_dir, "artifacts/pareto_archive.json")
    validation = artifacts.read_json(ctx.run_dir, "artifacts/validation.json")
    vs, _attacks, evals = variants(ctx)
    norm = normative_parameters(ctx)
    c = build(vs, om.epsilon, nm.robustness, norm, objectives_for("C_SHALLOW"))
    r = build(vs, om.epsilon, nm.robustness, norm, objectives_for("R"))
    names = {s["key"]: s["name"] for s in archive["solutions"]}
    baselines = {v.key for v in vs if v.baseline}
    sq = next(s for s in c.solutions if s.family == "STATUS_QUO")
    premium = legacy_premium(r.front, c.front, baselines)
    gate = phase_gate(validation["gates"], validation["falsification"])
    regime = ctx.manifest.constitutional_regime.regime_id.value
    ontologies = [o.ontology_id for o in ctx.manifest.ontology_set]
    vintages = sorted({str(s.manifest.temporal_start) for s in ctx.manifest.data_manifest
                       if "population_measurement" in s.use.roles and s.manifest.temporal_start is not None})
    lib = frozen_library(ctx)
    category = validation["publication_category"]
    channels = next(iter(evals.values()))["channels"]
    kept = [*HYBRID_KEPT]
    if channels["national_identity"]:
        kept.append("identités nationales observées, produites en partie par les frontières actuelles")
    front = []
    for k in c.front:
        s_pub = validation["stability"].get(k, {}).get("s_publish")
        front.append({"key": k, "name": names[k], "baseline": k in baselines,
                      "statement": statement(regime, ontologies, lib.freeze_hash, s_pub, category, True, vintages)})
    product = {
        "map_mode": "C_SHALLOW",
        "question": "quelle géométrie institutionnelle serait préférable aujourd'hui si les frontières actuelles "
                    "n'avaient aucune priorité juridique ?",
        "conclusion": c.conclusion, "front": front,
        "status_quo": {"rank": sq.rank, "on_front": sq.rank == 1,
                       "note": "géométrie actuelle évaluée comme une option parmi d'autres, sans privilège"},
        "unresolved": {names[k]: b for k, b in c.unresolved.items()},
        "improving_on_status_quo": [names[k] for k in c.improving],
        "legacy_premium": {k: [names[x] for x in xs] for k, xs in premium.items()},
        "map_r_conclusion_same_evaluations": r.conclusion,
        "hybrid": {"kept_from_x2026": kept, "removed": list(REMOVED),
                   "note": "contre-factuel contemporain, hybride par construction (01 §6) ; la dépendance "
                           "historique relève de Map-C-Deep (branche de recherche)"},
        "phase_gate": gate, "publication_category": category,
        "release_allowed": bool(validation["release_allowed"]) and gate["met"],
        "public_layer": {"published": False, "features": [],
                         "reason": f"catégorie {category}, phase 9 {gate['status']} : aucune frontière nette"},
        "valid_as_of": {"run_created_at": ctx.manifest.created_at.isoformat(), "data_vintages": vintages},
        "privacy_class": nm.privacy.default_access.value}
    artifacts.write_json(ctx.run_dir, "artifacts/map_c_shallow.json", product)
    record = ProvenanceRecord.create(
        "map_c.shallow", [f"validation:{content_hash(validation)}", f"pareto_archive:{content_hash(archive)}"],
        [f"map_c_shallow:{content_hash(product)}"], run_id=ctx.manifest.run_id)
    artifacts.write_provenance(ctx.run_dir, [record])
    ctx.repo.record_provenance([record])
    return {"count": len(front), "detail": f"{c.conclusion} front={len(front)} statu_quo_rang={sq.rank} "
                                           f"phase9={gate['status']}"}
