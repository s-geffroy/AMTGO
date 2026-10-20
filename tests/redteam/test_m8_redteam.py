"""Red-team M8 : candidats sans parts de groupes, pas de graine ethnographique, rien de publié."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from amtgo.config.settings import Settings
from amtgo.errors import AMTGOError
from amtgo.runs.queue import submit

SRC = Path(__file__).resolve().parents[2] / "src" / "amtgo"
GENERATOR_MODULES = [SRC / "candidates" / "generate.py", SRC / "candidates" / "model.py",
                     SRC / "runs" / "candidate_stages.py"]


def _names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
    return out


def test_generator_never_reads_group_composition() -> None:
    """Les familles territoriales n'utilisent que population et géographie (pas de découpage identitaire)."""
    for path in GENERATOR_MODULES:
        names = _names(path)
        assert "amtgo.measurement.composition" not in names, path
        assert not any("composition__" in n for n in names), path
        assert "amtgo.identity.state" not in names, path


def test_public_map_never_reads_candidates() -> None:
    names = _names(SRC / "export" / "pages_map.py")
    assert not any(n.startswith("amtgo.candidates") or n == "amtgo.runs.candidate_stages" for n in names)
    assert not any("candidates.npz" in n or "candidate_ensemble" in n for n in names)


def test_ethnographic_map_cannot_seed_candidates(settings: Settings, configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_pilot.yaml").read_text())
    for s in data["sources"]:
        if s["manifest"].endswith("synthetic_historical_map.yaml"):
            s["roles"] = [*s["roles"], "historical_boundary_seed"]
    p = configs_dir / "runs" / "ethno_seed.yaml"
    p.write_text(yaml.safe_dump(dict(data, name="ethno_seed")))
    with pytest.raises(AMTGOError, match="historical_boundary_seed"):
        submit(p, settings)


def test_reference_mesh_must_be_in_run(settings: Settings, configs_dir: Path) -> None:
    p = configs_dir / "candidates" / "pilot_v1.yaml"
    p.write_text(p.read_text().replace("reference_mesh: pilot_grid_l5", "reference_mesh: absent_mesh"))
    with pytest.raises(AMTGOError, match="absent_mesh"):
        submit(configs_dir / "runs" / "synthetic_pilot.yaml", settings)
