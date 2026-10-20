"""Red-team M3 : statut de preuve, vérité inaccessible au réel, rôles, mondes mêlés."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from amtgo.config.loader import load_model
from amtgo.data.sources import load_source_manifest
from amtgo.errors import ConfigurationError, ForbiddenSourceRole
from amtgo.manifests.run import RunRequest, resolve_request
from amtgo.measurement.validation import ground_truth_world


def test_no_ground_truth_for_real_sources(configs_dir: Path) -> None:
    ne = load_source_manifest(configs_dir / "sources" / "natural_earth_admin0.yaml")
    survey = load_source_manifest(configs_dir / "sources" / "synthetic_survey.yaml")
    assert ground_truth_world([survey]) is not None
    assert ground_truth_world([survey, ne]) is None  # un seul source réelle suffit : pas de vérité
    assert ground_truth_world([]) is None


def test_mixed_worlds_refused(configs_dir: Path) -> None:
    p = configs_dir / "sources" / "synthetic_census.yaml"
    p.write_text(p.read_text().replace("seed: 20251020", "seed: 1"))
    with pytest.raises(ConfigurationError):
        resolve_request(load_model(RunRequest, configs_dir / "runs" / "synthetic_pilot.yaml"), configs_dir)


def test_natural_earth_cannot_measure_population(configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "pages_africa.yaml").read_text())
    data["sources"][0]["roles"].append("population_measurement")
    with pytest.raises(ForbiddenSourceRole):
        resolve_request(RunRequest.model_validate(data), configs_dir)


def test_measurement_role_must_be_declared(configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_pilot.yaml").read_text())
    data["sources"][1]["roles"] = ["multiscale_validation"]
    with pytest.raises(ConfigurationError):
        resolve_request(RunRequest.model_validate(data), configs_dir)


def test_field_is_never_direct_evidence(tmp_path: Path, configs_dir: Path) -> None:
    import json

    from amtgo.config.settings import Settings
    from amtgo.db.repository import NullRepository
    from amtgo.runs.queue import run_to_completion, runs_dir, submit

    s = Settings(state_dir=tmp_path / "st", configs_dir=configs_dir, db_host=None)
    m, _ = submit(configs_dir / "runs" / "light_measure.yaml", s)
    assert run_to_completion(s, NullRepository(), str(m.run_id)).status.value == "SUCCEEDED"
    meta = json.loads((runs_dir(s) / str(m.run_id) / "fields" / "pilot_grid_l4" / "field.json").read_text())
    assert meta["evidence_status"] == "M"
