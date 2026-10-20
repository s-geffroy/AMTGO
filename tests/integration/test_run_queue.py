"""Intégration M0–M2 : file de runs, reprise après interruption, reproductibilité."""

from __future__ import annotations

import json
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
    assert cf["measurement_freeze"] == freeze_hash_of(d) and len(cf["effects"]) == 5
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
    assert "Candidate generation" in report and "non évalués" in report
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
    assert {layer["id"] for layer in meta["layers"]} >= {"countries", "boundaries", "mesh_mini_h3_r3"}


def test_mesh_extent_requires_declared_role(settings: Settings, ne_mini: Path) -> None:
    import yaml

    from amtgo.errors import ConfigurationError

    data = yaml.safe_load(ne_mini.read_text())
    data["sources"][0]["roles"] = ["basemap_display"]
    ne_mini.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigurationError):
        submit(ne_mini, settings)
