"""Red-team M4 : pas de vérité canonique, pas d'étiquette, vie privée de groupe."""

from __future__ import annotations

import inspect
import json
import pkgutil
import re
from pathlib import Path

import pytest
import yaml

import amtgo
from amtgo.config.settings import Settings
from amtgo.db.repository import NullRepository
from amtgo.errors import ConfigurationError, ForbiddenSourceRole
from amtgo.manifests.run import RunRequest, resolve_request
from amtgo.runs.queue import run_to_completion, runs_dir, submit

_FORBIDDEN = re.compile(r"(dominant|majorit|ethnic_label|ethnicity_of|main_language|label_cells|"
                        r"assign_group|group_of_cell|ethnic_state|homogene|homogeneity)", re.I)


def test_no_labelling_api_anywhere() -> None:
    """prompt §17, §20, §92 : aucune fonction publique ne renvoie l'étiquette d'une zone."""
    offenders = []
    for mod in pkgutil.walk_packages(amtgo.__path__, "amtgo."):
        if mod.name.startswith("amtgo.data.synthetic_world"):
            continue  # simule une carte historique défaillante, n'est pas une sortie d'analyse
        module = __import__(mod.name, fromlist=["_"])
        for name, obj in vars(module).items():
            if (inspect.isfunction(obj) or inspect.isclass(obj)) and not name.startswith("_") \
                    and _FORBIDDEN.search(name):
                offenders.append(f"{mod.name}.{name}")
    assert not offenders, offenders


def test_historical_map_cannot_feed_composition(configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_pilot.yaml").read_text())
    data["sources"][2]["roles"].append("composition_measurement")
    with pytest.raises(ForbiddenSourceRole):
        resolve_request(RunRequest.model_validate(data), configs_dir)


def test_composition_requires_population_model(configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_pilot.yaml").read_text())
    data.pop("measurement_model")
    with pytest.raises(ConfigurationError):
        resolve_request(RunRequest.model_validate(data), configs_dir)


def test_composition_role_must_be_declared(configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_pilot.yaml").read_text())
    data["sources"][0]["roles"].remove("composition_measurement")
    with pytest.raises(ConfigurationError):
        resolve_request(RunRequest.model_validate(data), configs_dir)


def test_group_fields_are_controlled_and_never_in_public_map(tmp_path: Path, configs_dir: Path) -> None:
    s = Settings(state_dir=tmp_path / "st", configs_dir=configs_dir, db_host=None)
    m, _ = submit(configs_dir / "runs" / "light_measure.yaml", s)
    assert run_to_completion(s, NullRepository(), str(m.run_id)).status.value == "SUCCEEDED"
    d = runs_dir(s) / str(m.run_id)
    meta = json.loads((d / "fields" / "pilot_grid_l4" / "composition.json").read_text())
    assert meta["privacy_class"] in ("CONTROLLED", "SENSITIVE", "PROHIBITED")
    assert meta["evidence_status"] == "M"
    report = (d / "report.md").read_text()
    assert "Parts seulement" in report and "aucune part par cellule" in report
    # L'export public de la carte n'a aucune couche de composition.
    import amtgo.export.pages_map as pm

    assert "composition" not in inspect.getsource(pm)


def test_errors_never_leak_bound_parameters() -> None:
    """Régression : une erreur SQL recopiait toutes les valeurs liées dans les logs et l'état."""
    from sqlalchemy.exc import DataError

    from amtgo.runs.queue import MAX_ERROR_CHARS, safe_error

    orig = ValueError("invalid input syntax for type uuid: \"synth_self_id\"\nLINE 1: ...")
    exc = DataError("INSERT INTO observations ...", [{"attributes": '{"counts": {"alpha": 8}}'}], orig)
    msg = safe_error(exc)
    assert "counts" not in msg and "alpha" not in msg and "INSERT" not in msg
    assert "invalid input syntax" in msg
    assert len(safe_error(RuntimeError("x" * 5000))) <= MAX_ERROR_CHARS
