"""Red-team M13 : Map-C-Shallow n'est ni une carte « vraie », ni un Map-C-Deep déguisé, ni une trajectoire."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from amtgo.config.settings import Settings
from amtgo.errors import ConfigurationError
from amtgo.runs.queue import submit

SRC = Path(__file__).resolve().parents[2] / "src" / "amtgo"


def _variant(configs_dir: Path, **changes: object) -> Path:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_c_shallow.yaml").read_text())
    data.update(changes)
    p = configs_dir / "runs" / "variant.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_no_transition_from_g0_without_legacy(settings: Settings, configs_dir: Path) -> None:
    with pytest.raises(ConfigurationError, match="Map-R"):
        submit(_variant(configs_dir, transition_model="transition/pilot_v1.yaml"), settings)


def test_c_deep_stays_a_research_branch(settings: Settings, configs_dir: Path) -> None:
    with pytest.raises(ConfigurationError, match="Map-C-Deep"):
        submit(_variant(configs_dir, map_mode="C_DEEP"), settings)


def test_map_c_never_exports_geometry() -> None:
    src = (SRC / "runs" / "map_c_stages.py").read_text()
    assert '"published": False, "features": []' in src
    assert "hybrid" in src and "kept_from_x2026" in src  # le contre-factuel déclare ce qu'il conserve


def test_legacy_removal_is_exactly_the_transition_term() -> None:
    """Retirer le privilège ne retire ni les droits, ni la viabilité, ni les coûts réels."""
    from amtgo.optimization.objectives import OBJECTIVES, objectives_for

    removed = set(OBJECTIVES) - set(objectives_for("C_SHALLOW"))
    assert removed == {"J_T"}
    assert {"J_D", "J_V", "J_inst"} <= set(objectives_for("C_SHALLOW"))
