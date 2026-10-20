"""Red-team M7 : pas de coefficient en dur, pas d'effet hors gel, rôles des sources causales."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from amtgo.config.settings import Settings
from amtgo.errors import ConfigurationError
from amtgo.manifests.run import RunManifest
from amtgo.runs.queue import submit
from amtgo.runs.stages import plan_steps


def test_effects_are_references_not_numbers() -> None:
    """prompt §33 : les modèles consommateurs ne portent que des clés d'effets, jamais des coefficients."""
    from amtgo.manifests.dfi import ReificationSpec
    from amtgo.manifests.viability import ViabilityEffects

    for model in (ViabilityEffects,):
        assert all(f.annotation is str for f in model.model_fields.values())
    assert ReificationSpec.model_fields["effect"].annotation is str


def test_missing_effect_refused_at_submission(settings: Settings, configs_dir: Path) -> None:
    p = configs_dir / "viability" / "pilot_v1.yaml"
    p.write_text(p.read_text().replace("market_access_elasticity: market_access_fiscal_elasticity",
                                       "market_access_elasticity: invented_coefficient"))
    with pytest.raises(ConfigurationError, match="invented_coefficient"):
        submit(configs_dir / "runs" / "synthetic_pilot.yaml", settings)


def test_viability_without_library_refused(settings: Settings, configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_pilot.yaml").read_text())
    data.pop("causal_library")
    p = configs_dir / "runs" / "no_library.yaml"
    p.write_text(yaml.safe_dump(dict(data, name="no_library")))
    with pytest.raises(ConfigurationError, match="absents de la bibliothèque"):
        submit(p, settings)


def test_panel_source_needs_estimation_role(settings: Settings, configs_dir: Path) -> None:
    data = yaml.safe_load((configs_dir / "runs" / "synthetic_pilot.yaml").read_text())
    data["sources"] = [s for s in data["sources"] if "synthetic_policy_panel.yaml" not in s["manifest"]]
    p = configs_dir / "runs" / "no_panel.yaml"
    p.write_text(yaml.safe_dump(dict(data, name="no_panel")))
    with pytest.raises(ConfigurationError, match="causal_estimation"):
        submit(p, settings)


def test_declared_effect_cannot_claim_strong_grade(configs_dir: Path) -> None:
    from amtgo.causal.library import CausalLibraryManifest
    from amtgo.config.loader import load_model

    p = configs_dir / "causal" / "library_pilot.yaml"
    p.write_text(p.read_text().replace("    design: expert_hypothesis\n    grade: I7",
                                       "    design: randomized\n    grade: I1", 1))
    with pytest.raises(ConfigurationError, match="s'estime"):
        load_model(CausalLibraryManifest, p)


def test_freeze_precedes_every_consumer(settings: Settings, configs_dir: Path) -> None:
    """prompt §32 : measurement_freeze → causal_freeze → tout consommateur d'effet."""
    m, _ = submit(configs_dir / "runs" / "synthetic_pilot.yaml", settings)
    assert isinstance(m, RunManifest)
    steps = plan_steps(m)
    freeze = steps.index("causal_freeze")
    assert steps.index("measurement_freeze") < freeze
    consumers = [i for i, s in enumerate(steps) if s.startswith(("dfi:", "viability:"))]
    assert consumers and min(consumers) > freeze
    assert all(steps.index(s) < freeze for s in steps if s.startswith("causal_estimate:"))
