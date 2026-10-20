"""M0 : manifeste normatif, régimes, RunManifest gelé et hashé."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from amtgo.config.loader import load_model
from amtgo.errors import ConfigurationError, ReproducibilityError
from amtgo.institutions.regimes import RegimeId, load_regime, normalize_regime_id
from amtgo.manifests.normative import NormativeManifest
from amtgo.manifests.run import RunRequest, resolve_request, verify_manifest


def _normative(configs_dir: Path) -> dict:
    return yaml.safe_load((configs_dir / "normative" / "default.yaml").read_text())


def test_default_normative_loads(configs_dir: Path) -> None:
    m = load_model(NormativeManifest, configs_dir / "normative" / "default.yaml")
    assert m.rights.severe_domination_probability_max == 0.05
    assert m.consent.model_may_infer_final_consent is False
    assert m.optimization.reification_penalty_enabled is True


@pytest.mark.parametrize("path,value", [
    (("consent", "model_may_infer_final_consent"), True),
    (("optimization", "state_count_penalty_enabled"), True),
    (("privacy", "default_access"), "PUBLIC"),
])
def test_normative_invariants_refused(configs_dir: Path, path: tuple[str, str], value: object) -> None:
    data = _normative(configs_dir)
    data[path[0]][path[1]] = value
    with pytest.raises(ValueError):
        NormativeManifest.model_validate(data)


def test_hard_right_not_relaxable(configs_dir: Path) -> None:
    data = _normative(configs_dir)
    data["hard_rights"][0]["relaxable"] = True
    with pytest.raises(ValueError):
        NormativeManifest.model_validate(data)


@pytest.mark.parametrize("alias,expected", [
    ("R0", RegimeId.R0_CURRENT_LIKE), ("R0_CURRENT", RegimeId.R0_CURRENT_LIKE),
    ("r3_federal", RegimeId.R3_FEDERAL_CONTINENTAL), ("R2_CONFEDERAL", RegimeId.R2_CONFEDERAL),
])
def test_regime_aliases(alias: str, expected: RegimeId) -> None:
    assert normalize_regime_id(alias) is expected


def test_all_regimes_load(configs_dir: Path) -> None:
    for rid in RegimeId:
        assert load_regime(configs_dir, rid.value).regime_id is rid
    with pytest.raises(ConfigurationError):
        normalize_regime_id("R9")


def _request(configs_dir: Path) -> RunRequest:
    return load_model(RunRequest, configs_dir / "runs" / "synthetic_pilot.yaml")


def test_run_manifest_stable(configs_dir: Path) -> None:
    a = resolve_request(_request(configs_dir), configs_dir)
    b = resolve_request(_request(configs_dir), configs_dir)
    assert a.run_id == b.run_id and a.manifest_hash == b.manifest_hash
    assert a.measurement_model is not None  # le pilote déclare un modèle de mesure (M3)
    assert a.causal_library is None and a.solver is None
    verify_manifest(a)


def test_run_manifest_changes_with_config(configs_dir: Path) -> None:
    a = resolve_request(_request(configs_dir), configs_dir)
    p = configs_dir / "sources" / "synthetic_survey.yaml"
    p.write_text(p.read_text().replace("n_ea: 300", "n_ea: 301"))
    b = resolve_request(_request(configs_dir), configs_dir)
    assert a.run_id != b.run_id


def test_tampered_manifest_detected(configs_dir: Path) -> None:
    m = resolve_request(_request(configs_dir), configs_dir)
    tampered = m.model_copy(update={"seeds": (1, 2)})
    with pytest.raises(ReproducibilityError):
        verify_manifest(tampered)


def test_no_neutral_run(configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_pilot.yaml").read_text())
    del data["constitutional_regime"]
    with pytest.raises(ValueError):
        RunRequest.model_validate(data)


def test_c_deep_refused(configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_pilot.yaml").read_text())
    data["map_mode"] = "C_DEEP"
    with pytest.raises(ConfigurationError):
        resolve_request(RunRequest.model_validate(data), configs_dir)
