"""Red-team M6 : pas de viabilité hors contexte, pas de plan de coercition, garde-fous de déplacement."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from amtgo.config.settings import Settings
from amtgo.errors import ConfigurationError
from amtgo.runs.queue import submit

SRC = Path(__file__).resolve().parents[2] / "src" / "amtgo"


def _functions() -> list[tuple[str, str, list[str]]]:
    out = []
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                out.append((str(path.relative_to(SRC)), node.name, [a.arg for a in node.args.args]))
    return out


def test_no_context_free_viability() -> None:
    """prompt §29 : jamais ``is_viable(territory)`` ; toute viabilité prend régime et scénario."""
    fns = _functions()
    assert not [f for f in fns if "is_viable" in f[1]]
    compute = [f for f in fns if f[1] == "compute_viability"]
    assert compute and all({"regime", "scenario"} <= set(args) for _, _, args in compute)


def test_no_homogeneity_maximization_or_displacement_planning() -> None:
    """prompt §92-93 : aucune fonction ne maximise l'homogénéité ni ne planifie des déplacements."""
    forbidden = ("maximize_ethnic", "homogeneity_max", "maximize_homogeneity", "plan_relocation",
                 "relocation_plan", "displacement_plan", "assign_people", "route_population")
    bad = [f for f in _functions() if any(w in f[1].lower() for w in forbidden)]
    assert not bad, bad


def test_coercion_module_exposes_no_origin_destination() -> None:
    from amtgo.scenarios import coercion

    names = " ".join(dir(coercion)).lower()
    for word in ("origin", "destination", "route", "schedule", "calendar", "who_moves"):
        assert word not in names


def _pilot(configs_dir: Path) -> dict:  # type: ignore[type-arg]
    return dict(yaml.safe_load((configs_dir / "runs" / "synthetic_pilot.yaml").read_text()))


def _write(configs_dir: Path, name: str, data: dict) -> Path:  # type: ignore[type-arg]
    p = configs_dir / "runs" / f"{name}.yaml"
    p.write_text(yaml.safe_dump(dict(data, name=name)))
    return p


def test_forced_migration_scenario_refused_at_submission(settings: Settings, configs_dir: Path) -> None:
    p = configs_dir / "scenarios" / "s1_baseline.yaml"
    p.write_text(p.read_text().replace("forced_migration: 0.0", "forced_migration: 5000.0"))
    with pytest.raises(ConfigurationError, match="forced_migration"):
        submit(configs_dir / "runs" / "synthetic_pilot.yaml", settings)


def test_viability_requires_a_non_coercive_scenario(settings: Settings, configs_dir: Path) -> None:
    data = _pilot(configs_dir)
    data["scenario_set"] = ["scenarios/s2c_diagnostic.yaml"]
    with pytest.raises(ConfigurationError, match="S1 ou S2A"):
        submit(_write(configs_dir, "only_s2c", data), settings)
    data["scenario_set"] = []
    with pytest.raises(ConfigurationError):
        submit(_write(configs_dir, "no_scenario", data), settings)


def test_fiscal_source_needs_declared_role(settings: Settings, configs_dir: Path) -> None:
    """Les totaux de population du recensement ne deviennent pas des comptes fiscaux par erreur."""
    p = configs_dir / "viability" / "pilot_v1.yaml"
    p.write_text(p.read_text().replace("fiscal_source: synthetic_fiscal", "fiscal_source: synthetic_census"))
    with pytest.raises(ConfigurationError, match="viability_inputs"):
        submit(configs_dir / "runs" / "synthetic_pilot.yaml", settings)


def test_duplicate_scenario_refused(settings: Settings, configs_dir: Path) -> None:
    data = _pilot(configs_dir)
    data["scenario_set"] = ["scenarios/s1_baseline.yaml", "scenarios/s1_baseline.yaml"]
    with pytest.raises(ConfigurationError, match="dupliqué"):
        submit(_write(configs_dir, "dup_scenario", data), settings)
