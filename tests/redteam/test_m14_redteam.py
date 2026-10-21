"""Red-team M14 : la coordination continentale n'est ni un solve monolithique, ni un transfert de coût caché."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from amtgo.config.settings import Settings
from amtgo.errors import ConfigurationError
from amtgo.manifests.continental import CoordinationLayer
from amtgo.runs.queue import submit

SRC = Path(__file__).resolve().parents[2] / "src" / "amtgo"


def _write(configs_dir: Path, rel: str, data: dict[str, Any]) -> str:
    (configs_dir / rel).write_text(yaml.safe_dump(data))
    return rel


def _continental(configs_dir: Path, **changes: Any) -> Path:
    data = yaml.safe_load((configs_dir / "continental" / "synthetic_continental.yaml").read_text())
    data.update(changes)
    p = configs_dir / "continental" / "variant.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def _east(configs_dir: Path, **changes: Any) -> str:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_east.yaml").read_text())
    return _write(configs_dir, "runs/east_variant.yaml", dict(data, name="east_variant", **changes))


def _regions(east: str) -> list[dict[str, str]]:
    return [{"region_id": "west", "run": "runs/smoke.yaml"}, {"region_id": "east", "run": east}]


def test_free_layer_is_a_hidden_cost_transfer() -> None:
    """05 §14 : une couche gratuite déplacerait un coût vers le niveau continental sans le compter."""
    base = {"layer_id": "market", "type": "market", "acts_on": "cross_links",
            "effect": "market_integration_link_mitigation"}
    with pytest.raises(ValidationError, match="gratuite"):
        CoordinationLayer.model_validate({**base, "annual_cost": {"lo": 0.0, "hi": 1.0}})
    with pytest.raises(ValidationError, match="hydrographie"):  # un bassin n'est pas inventé
        CoordinationLayer.model_validate({**base, "type": "basin", "annual_cost": {"lo": 1.0, "hi": 2.0}})


def test_incommensurable_regions_are_refused(settings: Settings, configs_dir: Path) -> None:
    east = _east(configs_dir, constitutional_regime="R2_CONFEDERAL")
    with pytest.raises(ConfigurationError, match="régime"):
        submit(_continental(configs_dir, regions=_regions(east)), settings)
    east = _east(configs_dir, mesh_set=["meshes/east_grid_l4.yaml"])
    with pytest.raises(ConfigurationError, match="maillage"):
        submit(_continental(configs_dir, regions=_regions(east)), settings)


def test_same_context_twice_is_double_counting(settings: Settings, configs_dir: Path) -> None:
    regions = [{"region_id": "west", "run": "runs/smoke.yaml"}, {"region_id": "west2", "run": "runs/smoke.yaml"}]
    with pytest.raises(ConfigurationError, match="comptée deux fois"):
        submit(_continental(configs_dir, regions=regions), settings)


def test_continental_library_has_no_estimation_and_no_transport(settings: Settings, configs_dir: Path) -> None:
    lib = yaml.safe_load((configs_dir / "causal" / "library_continental.yaml").read_text())
    pilot = yaml.safe_load((configs_dir / "causal" / "library_pilot.yaml").read_text())
    with_est = _write(configs_dir, "causal/lib_est.yaml", dict(lib, estimations=pilot["estimations"]))
    with pytest.raises(ConfigurationError, match="aucune estimation"):
        submit(_continental(configs_dir, causal_library=with_est), settings)
    # Les bornes basses sont nulles : aucune couche n'est présentée comme établie.
    assert all(d["bounds"]["lo"] == 0.0 for d in lib["declared"])


def test_map_r_only(settings: Settings, configs_dir: Path) -> None:
    regions = [{"region_id": "west", "run": "runs/synthetic_c_shallow.yaml"},
               {"region_id": "east", "run": "runs/synthetic_east.yaml"}]
    with pytest.raises(ConfigurationError, match="Map-R"):
        submit(_continental(configs_dir, regions=regions), settings)


def test_no_monolithic_solve_and_no_map() -> None:
    """07 §13 : aucune étape continentale ne génère ni n'évalue de partition ; rien n'est exporté."""
    src = (SRC / "runs" / "continental_stages.py").read_text() + (SRC / "optimization" / "continental.py").read_text()
    for forbidden in ("candidate_partition", "spectral_partition", "community_partition", "evaluate_geometry",
                      "generate_candidates"):
        assert forbidden not in src
    assert '"published": False, "features": []' in src
    assert not re.search(r"\b(best_solution|argmin|optimal|is_viable|maximize_ethnic)", src)
