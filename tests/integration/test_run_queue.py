"""Intégration M0–M2 : file de runs, reprise après interruption, reproductibilité."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from amtgo.config.settings import Settings
from amtgo.db.repository import NullRepository
from amtgo.runs.queue import advance_one, list_runs, run_to_completion, runs_dir, submit
from amtgo.runs.state import RunStatus, load_state


def _run(settings: Settings, request: str) -> str:
    manifest, created = submit(settings.configs_dir / request, settings)
    assert created
    state = run_to_completion(settings, NullRepository(), str(manifest.run_id))
    assert state.status is RunStatus.SUCCEEDED, state.error
    return str(manifest.run_id)


def test_synthetic_pilot_end_to_end(settings: Settings) -> None:
    """Pilote complet M0–M3 : propriétés qualitatives (ADR-0010), pas de valeurs figées."""
    run_id = _run(settings, "runs/synthetic_pilot.yaml")
    d = runs_dir(settings) / run_id
    report = (d / "report.md").read_text()
    assert "NOT_IDENTIFIABLE" in report and "CAUSAL_EFFECT_UNKNOWN" in report
    assert "prouve" not in report  # 06 §15
    assert "WE ASSUME" in report and "WE DO NOT KNOW" in report
    ms = json.loads((d / "artifacts" / "multiscale.json").read_text())
    assert set(ms["meshes"]) == {"pilot_h3_r5", "pilot_h3_r6", "pilot_grid_l4", "pilot_grid_l5"}
    for t in ms["transfers"]:
        assert t["mass_out"] + t["unallocated"] == pytest.approx(t["mass_in"], rel=1e-6)
    for mid in ms["meshes"]:
        field = json.loads((d / "fields" / mid / "field.json").read_text())
        val = json.loads((d / "fields" / mid / "validation.json").read_text())
        assert field["evidence_status"] == "M" and field["laplace"]["converged"]
        cal = val["calibration"]
        assert cal["total_covered"]  # le total vrai est dans l'intervalle
        assert 0.8 <= cal["cell_coverage"] <= 0.99  # ni sur- ni sous-confiant à l'excès
        assert val["holdout"]["coverage"] >= 0.8
        # L'ablation : l'enquête seule est moins informative sur le total que la fusion.
        ab = val["ablation"]
        width = {k: v["total_interval"][1] - v["total_interval"][0] for k, v in ab.items()}
        assert width["synthetic_survey"] > width["synthetic_census+synthetic_survey"]
    cmp_ = json.loads((d / "artifacts" / "fields_comparison.json").read_text())
    assert cmp_["max_abs_z"] < 3.0  # maillages compatibles à 100 km
    # L'information croît avec l'échelle : ce qui est D à la cellule peut être A/B à 100 km.
    for mid, v in cmp_["reference_scale_information"].items():
        cell = json.loads((d / "fields" / mid / "field.json").read_text())["median_information_ratio"]
        assert v["median"] > cell
    # M4 : composition sous deux ontologies — propriétés qualitatives (ADR-0010).
    for mid in ms["meshes"]:
        c = json.loads((d / "fields" / mid / "composition.json").read_text())
        assert c["privacy_class"] in ("CONTROLLED", "SENSITIVE", "PROHIBITED")
        assert c["calibration"]["reference_coverage"] >= 0.8
        assert 0.0 <= c["ontology_stability"]["s_ontology"] <= 1.0
        # Une carte à étiquette unique ne représente qu'une partie de la population du bloc.
        assert c["historical_label_check"]["synth_ext_hist"]["mean_label_share"] < 0.8
    # M5 : D/F/I du statu quo, CONTROLLED, canaux sans données UNKNOWN, D réalisé UNKNOWN.
    for mid in ms["meshes"]:
        dfi = json.loads((d / "fields" / mid / "dfi.json").read_text())
        assert dfi["privacy_class"] == "CONTROLLED" and dfi["evidence_status"] == "M"
        for o in dfi["ontologies"].values():
            assert "mobility" in o["unknown_fragmentation_channels"]
            assert "territorial" in o["unknown_fragmentation_channels"]
            assert o["domination"]["realized_component"].startswith("UNKNOWN")
            assert 0.0 <= o["integration"]["j_conn"]["mean"] <= 1.0
    ens = json.loads((d / "artifacts" / "dfi_ensemble.json").read_text())
    assert 0.0 <= ens["s_ontology_dfi"] <= 1.0 and 0.0 <= ens["s_scale_dfi"] <= 1.0
    assert "Domination, fragmentation, integration" in report
    # M6 : viabilité conditionnelle (régime, scénario), garde-fous, S2C agrégé seulement.
    for mid in ms["meshes"]:
        via = json.loads((d / "fields" / mid / "viability.json").read_text())
        assert set(via["assessments"]) == {"s1_baseline", "s1_stress", "s2a_voluntary"}  # jamais S2C
        for g in via["guards"].values():
            assert g["forced_migration"] == 0.0 and g["reform_induced_relocation"] == 0.0
        assert via["guards"]["s2a_voluntary"]["voluntary_response"] == "CAUSAL_EFFECT_UNKNOWN"
        for by_r in via["assessments"].values():
            assert set(by_r) == {"R0_CURRENT_LIKE", "R1_COMMON_MARKET", "R2_CONFEDERAL", "R3_FEDERAL_CONTINENTAL"}
            for rid, by_t in by_r.items():
                for a in by_t.values():
                    assert rid in a["statement"] and "scénario" in a["statement"]
    vens = json.loads((d / "artifacts" / "viability_ensemble.json").read_text())
    assert 0.0 <= vens["s_scale_viability"] <= 1.0
    s2c = json.loads((d / "artifacts" / "s2c_diagnostic.json").read_text())
    assert s2c["s2c_diagnostic"]["status"] == "NOT_APPLICABLE"
    assert "Contextual viability" in report and "Non disponible à ce stade (milestone M6)" not in report
    # M7 : bibliothèque estimée, validée, gelée ; adoption endogène rejetée ; Gate C.
    cv = json.loads((d / "artifacts" / "causal_validation.json").read_text())
    assert cv["gate_c"] == "PASSED"
    assert cv["rejected"] == ["language_rights_index_fictive"]
    assert cv["estimations"]["fiscal_decentralization_service_coverage"]["synthetic_truth"]["covered"]
    assert not cv["estimations"]["language_rights_index_fictive"]["synthetic_truth"]["covered"]
    cf = json.loads((d / "causal_freeze.json").read_text())
    assert cf["measurement_freeze"] == freeze_hash_of(d) and len(cf["effects"]) == 10
    for mid in ms["meshes"]:
        effects = json.loads((d / "fields" / mid / "viability.json").read_text())["effects"]
        assert {v["status"] for v in effects.values()} == {"EXPLORATORY_ONLY"}
    assert "Gate C : PASSED" in report and "CAUSAL_EFFECT_UNKNOWN" in report
    # M8 : baselines toujours présentes, candidats contigus, stabilité multi-échelle, rien de recommandé.
    for mid in ms["meshes"]:
        cands = json.loads((d / "fields" / mid / "candidates.json").read_text())
        families = {c["family"] for c in cands["candidates"]}
        assert {"STATUS_QUO", "NO_TERRITORIAL_CHANGE", "INSTITUTIONAL_ONLY_REFORM"} <= families
        assert all(c["contiguous"] for c in cands["candidates"])
        assert set(cands["unavailable_families"]) == {"HISTORICAL", "LANGUAGE", "MOBILITY"}
    ce = json.loads((d / "artifacts" / "candidate_ensemble.json").read_text())
    assert ce["recommendation_status"] == "NOT_IDENTIFIABLE"
    sq = next(v for v in ce["variants"].values() if v["family"] == "STATUS_QUO")
    assert sq["s_scale"] >= 0.8  # le statu quo suit des districts : stable entre maillages
    assert {v["n_states_by_mesh"]["pilot_grid_l4"] for v in ce["variants"].values()
            if v["family"] == "GEOGRAPHIC"} == {1, 2, 3, 4}
    assert "Candidate generation" in report and "unités analytiques" in report
    # M9 : composeur à géométrie fixe ; le statu quo fictif ne viole aucun droit → NO_CHANGE, stable.
    ie = json.loads((d / "artifacts" / "institutional_ensemble.json").read_text())
    assert ie["conclusion"] == "NO_CHANGE" and ie["stability"] == "STABLE"
    for mid in ms["meshes"]:
        comp = json.loads((d / "fields" / mid / "institutional_composition.json").read_text())
        for res in comp["ontologies"].values():
            assert res["deferred_to_territorial_search"] == ["confederation", "sovereignty"]
            assert all(o["status"] in ("NOT_NEEDED", "CREATES_VIOLATION") for o in res["options"])
    assert "Institutional composition (fixed geometry)" in report
    # M10 : archive robuste, baselines au front, J_R UNKNOWN, Gate O, rien de publiable.
    pa = json.loads((d / "artifacts" / "pareto_archive.json").read_text())
    sq = next(s for s in pa["solutions"] if s["family"] == "STATUS_QUO")
    assert sq["feasible"] and sq["rank"] == 1  # coût de transition nul : le statu quo n'est jamais exclu
    assert all(s["objectives"]["J_R"] is None for s in pa["solutions"])
    assert pa["gate_o"] == "PASSED" and pa["recommendation_status"] == "NOT_IDENTIFIABLE"
    assert pa["known_biases"] and pa["infeasibility"] is None
    assert sum(1 for s in pa["solutions"] if s["rank"] == 1) > 1  # un front, jamais une solution unique
    assert "Archive de Pareto **robuste**" in report and "Biais connus" in report
    # M11 : objectifs inconnus → dominance non résolue ; gates ; rien de publiable ; red-team passé.
    assert pa["conclusion"] in ("DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES", "NO_TERRITORIAL_CHANGE")
    assert all(s["objectives"]["J_P"] is None for s in pa["solutions"])
    va = json.loads((d / "artifacts" / "validation.json").read_text())
    assert set(va["gates"]) == {"M", "C", "O", "S", "R"} and va["gates"]["S"] == "PASSED"
    assert va["gates"]["O"] == "PASSED" and va["goodhart"]["status"] == "PASSED"  # aucune faille ouverte
    assert va["s_publish"] is None and va["gates"]["R"] == "NOT_EVALUABLE"  # S^time inconnu
    assert va["publication_category"] == "NOT_IDENTIFIABLE" and not va["release_allowed"]
    assert all(c["status"] != "FAILED" for c in va["falsification"])
    assert all(a["blocked"] for a in va["privacy"]["attacks"])
    assert {x["layer"] for x in va["privacy"]["inventory"] if x["action"] == "allow"} == \
        {f"mesh_{m}" for m in ms["meshes"]}  # seuls les maillages sortiraient tels quels
    assert len(va["sensitivity"]["settings"]) == 10 and {a["ablation"] for a in va["ablations"]} >= {"D", "F", "I"}
    assert "Validation & red-team" in report
    # M12 : Map-R — trajectoires depuis le statu quo, transition comprise ; rien de cartographié.
    mr = json.loads((d / "artifacts" / "map_r.json").read_text())
    sq_path = next(p for p in mr["paths"] if p["path_id"] == "path:status_quo")
    assert sq_path["rank"] == 1 and sq_path["feasible"]  # rester est toujours une option du front
    assert mr["conclusion"] in ("STATUS_QUO_NOT_DOMINATED", "UNRESOLVED_UNKNOWN_OBJECTIVES")
    assert mr["hierarchy"][0]["action"] == "no_change" and len(mr["hierarchy"]) == 8
    assert not mr["public_layer"]["published"] and mr["public_layer"]["features"] == []
    assert all("consentement politique externe" in p["statement"] for p in mr["paths"])
    assert {p["family"] for p in mr["paths"]} >= {"STATUS_QUO", "PATH_INSTITUTIONAL", "PATH_TERRITORIAL"}
    assert "## Map-R (régional)" in report
    for word in ("devrait devenir", "prouve que", "recommandée"):
        assert word not in report.lower()
    freeze = json.loads((d / "measurement_freeze.json").read_text())
    assert set(freeze["compositions"]) == set(ms["meshes"])
    assert "Parts seulement" in report
    assert (d / "measurement_freeze.json").exists()
    assert len(list((d / "provenance").glob("*.json"))) >= 12


def freeze_hash_of(run_dir: Path) -> str:
    return str(json.loads((run_dir / "measurement_freeze.json").read_text())["freeze_hash"])


def test_resubmission_is_idempotent(settings: Settings) -> None:
    a, created_a = submit(settings.configs_dir / "runs/light.yaml", settings)
    b, created_b = submit(settings.configs_dir / "runs/light.yaml", settings)
    assert created_a and not created_b and a.run_id == b.run_id
    assert len(list_runs(settings)) == 1


def test_interrupted_step_resumes(settings: Settings) -> None:
    manifest, _ = submit(settings.configs_dir / "runs/light.yaml", settings)
    rid = str(manifest.run_id)
    repo = NullRepository()
    assert advance_one(settings, repo).outcome == "done"  # type: ignore[union-attr]
    # SIGTERM pendant l'ingestion : l'étape est rejouée, sans compter comme échec.
    adv = advance_one(settings, repo, should_stop=lambda: True)
    assert adv is not None and adv.outcome == "interrupted"
    state = load_state(runs_dir(settings) / rid)
    assert state.steps[1].attempts == 0 and not state.steps[1].done
    final = run_to_completion(settings, repo, rid)
    assert final.status is RunStatus.SUCCEEDED


def test_reproducibility_same_manifest_same_outputs(tmp_path: Path, configs_dir: Path) -> None:
    """prompt §53 : même manifeste + même code ⇒ même résultat."""
    hashes = []
    for k in ("a", "b"):
        s = Settings(state_dir=tmp_path / k, configs_dir=configs_dir, db_host=None)
        rid = _run(s, "runs/synthetic_pilot.yaml")
        hashes.append(json.loads((runs_dir(s) / rid / "outputs.json").read_text())["outputs_hash"])
    assert hashes[0] == hashes[1]


def test_deterministic_failure_fails_fast(settings: Settings) -> None:
    p = settings.configs_dir / "sources" / "synthetic_survey.yaml"
    p.write_text(p.read_text().replace("n_ea: 300", "n_ea: oops"))
    manifest, _ = submit(settings.configs_dir / "runs/light.yaml", settings)
    state = run_to_completion(settings, NullRepository(), str(manifest.run_id))
    assert state.status is RunStatus.FAILED
    assert state.error and "n_ea" in state.error  # le message n'est jamais avalé


def test_transient_failure_retried(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from amtgo.runs import stages

    calls = {"n": 0}
    original = stages.STAGES["validate_sources"]

    def flaky(ctx, arg):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disque momentanément indisponible")
        return original(ctx, arg)

    monkeypatch.setitem(stages.STAGES, "validate_sources", flaky)
    manifest, _ = submit(settings.configs_dir / "runs/light.yaml", settings)
    adv = advance_one(settings, NullRepository())
    assert adv is not None and adv.outcome == "retry"
    final = run_to_completion(settings, NullRepository(), str(manifest.run_id))
    assert final.status is RunStatus.SUCCEEDED


def test_pages_export_from_fixture(settings: Settings, ne_mini: Path, tmp_path: Path) -> None:
    from amtgo.export.pages_map import export_pages_map

    rid = _run(settings, "runs/mini_pages.yaml")
    out = tmp_path / "map"
    meta = export_pages_map(runs_dir(settings) / rid, out)
    countries = json.loads((out / "countries.geojson").read_text())
    names = {f["properties"]["name"] for f in countries["features"]}
    assert names == {"Testland A", "Testland B"}  # filtre continent appliqué
    assert all("pop_est" not in f["properties"] for f in countries["features"])
    lines = json.loads((out / "boundaries.geojson").read_text())
    assert lines["features"][0]["properties"]["disputed"] is True
    cand = json.loads((out / "candidates.json").read_text())
    assert cand["status"] == "NOT_IDENTIFIABLE" and cand["candidates"] == []
    assert "prototype de mesure de la population" in cand["message"] and "M3" not in cand["message"]
    assert {layer["id"] for layer in meta["layers"]} >= {"countries", "boundaries", "mesh_mini_h3_r3"}


def test_mesh_extent_requires_declared_role(settings: Settings, ne_mini: Path) -> None:
    import yaml

    from amtgo.errors import ConfigurationError

    data = yaml.safe_load(ne_mini.read_text())
    data["sources"][0]["roles"] = ["basemap_display"]
    ne_mini.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigurationError):
        submit(ne_mini, settings)


def test_map_c_shallow_end_to_end(settings: Settings) -> None:
    """M13 : sans privilège juridique (J_T retiré), la société observée conservée et déclarée hybride."""
    run_id = _run(settings, "runs/synthetic_c_shallow.yaml")
    d = runs_dir(settings) / run_id
    pa = json.loads((d / "artifacts" / "pareto_archive.json").read_text())
    assert pa["map_mode"] == "C_SHALLOW" and "J_T" not in pa["objectives"]
    assert pa["legacy_objectives_removed"] == ["J_T"]
    assert all(s["objectives"]["J_T"] is None for s in pa["solutions"])
    mc = json.loads((d / "artifacts" / "map_c_shallow.json").read_text())
    # La géométrie actuelle n'est exclue que par une dominance établie : la fusion ne l'est jamais sur J_P.
    assert mc["status_quo"]["on_front"]
    assert mc["phase_gate"]["status"] == "RESEARCH_ONLY" and not mc["release_allowed"]
    assert not mc["public_layer"]["published"] and mc["hybrid"]["kept_from_x2026"]
    assert all("non prescriptif" in f["statement"] for f in mc["front"])
    assert not (d / "artifacts" / "map_r.json").exists()  # pas de trajectoires depuis G_0
    report = (d / "report.md").read_text()
    assert "## Map-C-Shallow" in report and "Prime de l'existant" in report and "prouve" not in report
    # La couche candidats de la carte dit pourquoi elle est vide, lu sur une validation réelle.
    from amtgo.export.pages_map import candidates_message

    msg = candidates_message(d)
    assert "catégorie NOT_IDENTIFIABLE" in msg and "M FAILED" in msg and "ROBUST ou CONDITIONAL" in msg


def test_continental_composition_end_to_end(settings: Settings) -> None:
    """M14 : deux runs Map-R régionaux composés à leur interface, sans solve monolithique."""
    manifest, created = submit(settings.configs_dir / "continental/synthetic_continental.yaml", settings)
    assert created
    order = [s.run_id for s in list_runs(settings)]
    regional = [str(r.run_id) for r in manifest.regions]  # type: ignore[union-attr]
    assert set(regional) < set(order) and order.index(str(manifest.run_id)) > max(order.index(r) for r in regional)
    state = run_to_completion(settings, NullRepository(), str(manifest.run_id))
    assert state.status is RunStatus.SUCCEEDED, state.error
    d = runs_dir(settings) / str(manifest.run_id)
    p = json.loads((d / "artifacts" / "continental.json").read_text())
    assert p["decomposition"]["monolithic"] is False
    assert all(e["checked"] and e["exact"] for e in p["decomposition"]["exactness"]), p["decomposition"]
    sq = next(f for f in p["front"] if f["status_quo"])
    assert sq["rank"] == 1 and p["conclusion"] in ("STATUS_QUO_NOT_DOMINATED",
                                                   "DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES")
    # Le coût de la frontière d'interface, invisible en région, est compté au niveau continental.
    itf = p["interfaces"][0]
    assert itf["border_km"] > 300 and p["costs_moved_to_continental_level"]["interface_border_management"] > 0
    # Borne basse nulle : aucune couche n'est établie ; la borne haute ne donne qu'une priorité de recherche.
    assert itf["layer_front_robust"] == [] and itf["verdict"] is None
    assert p["publication_category"] == "NOT_IDENTIFIABLE" and not p["public_layer"]["published"]
    report = (d / "report.md").read_text()
    assert "## Décomposition (07 §13)" in report and "## Régimes de conclusion (09 §14)" in report
    assert not re.search(r"\b(prouve|meilleur|optimal)", report)
    again, created = submit(settings.configs_dir / "continental/synthetic_continental.yaml", settings)
    assert not created and again.run_id == manifest.run_id


def test_c_deep_research_branch_end_to_end(settings: Settings) -> None:
    """Map-C-Deep : SCM historique validé, ensemble de formes structurelles, calibration, aucun produit."""
    run_id = _run(settings, "research/c_deep_synthetic.yaml")
    d = runs_dir(settings) / run_id
    p = json.loads((d / "artifacts" / "c_deep.json").read_text())
    assert p["status"] == "HISTORICAL_COUNTERFACTUAL — NON_PRESCRIPTIVE" and p["experimental"]
    assert p["conclusion"] == "HISTORICAL_COUNTERFACTUAL_ESTIMATED" and len(p["ensemble"]) >= 2
    assert p["calibration"]["status"] == "COVERED"
    assert not p["public_layer"]["published"] and p["privacy_class"] == "CONTROLLED"
    assert not any(k.startswith("group_share") for k in p["counterfactual"]["counterfactual"])
    groups = json.loads((d / "artifacts" / "c_deep_groups.json").read_text())
    assert groups["privacy_class"] == "CONTROLLED"
    report = (d / "report.md").read_text()
    assert "HISTORICAL_COUNTERFACTUAL — NON_PRESCRIPTIVE" in report and "group_share" not in report
    assert "nécessaire, pas suffisant" in report and not re.search(r"\b(prouve|meilleur|optimal)", report)
    for f in ("pareto_archive.json", "map_r.json", "continental.json"):
        assert not (d / "artifacts" / f).exists()
