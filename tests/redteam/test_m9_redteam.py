"""Red-team M9 (Goodhart, 05 §14) : le composeur ne s'achète pas de résultat."""

from __future__ import annotations

from pathlib import Path

import pytest

from amtgo.causal.library import CausalAnswer
from amtgo.causal.model import CAUSAL_EFFECT_UNKNOWN
from amtgo.config.settings import Settings
from amtgo.core.channels import IntegChannel
from amtgo.errors import ConfigurationError
from amtgo.institutions.composer import compose
from amtgo.manifests.normative import RightsThresholds
from amtgo.runs.queue import submit
from amtgo.validation import composer_worlds as I

RIGHTS = RightsThresholds(severe_domination_threshold=0.5, severe_domination_probability_max=0.05,
                          urgent_domination_threshold=0.7, urgent_probability=0.5)
WEIGHTS = {c: 1.0 for c in IntegChannel}


def test_unknown_effects_never_resolve_anything() -> None:
    """Sans effet identifié, aucun levier ne « résout » : le composeur ne conclut pas à la place des données."""
    st, part = I.world(0.15)
    unknown = {k: CausalAnswer(k, CAUSAL_EFFECT_UNKNOWN, None, None, "absent") for k in I.effects()}
    res = compose(st, part, I._institutions(part), RIGHTS, WEIGHTS, I.manifest(), unknown, I._adjacency(10, 6))
    assert {o["status"] for o in res["options"]} == {"CAUSAL_EFFECT_UNKNOWN"}
    assert res["conclusion"] == "INSTITUTIONAL_INSUFFICIENT_AT_FIXED_GEOMETRY" and res["chosen"] is None


def test_composer_never_changes_geometry() -> None:
    st, part = I.world(0.15)
    before = [lv.assignment.copy() for lv in part.levels]
    res = compose(st, part, I._institutions(part), RIGHTS, WEIGHTS, I.manifest(), I.effects(), I._adjacency(10, 6))
    assert all((a == lv.assignment).all() for a, lv in zip(before, part.levels, strict=True))
    assert res["deferred_to_territorial_search"] == ["sovereignty"]
    assert "border" not in res["conclusion"].lower() or res["conclusion"].startswith("NO_")


def test_cost_and_complexity_are_reported_not_hidden() -> None:
    st, part = I.world(0.15)
    res = compose(st, part, I._institutions(part), RIGHTS, WEIGHTS, I.manifest(), I.effects(), I._adjacency(10, 6))
    assert {"cost", "complexity"} <= set(res["objectives"])
    rights = next(o for o in res["options"] if o["option"] == "rights_enforcement")
    assert rights["lo"]["cost"] > res["baseline"]["cost"] and rights["lo"]["complexity"] > 0


def test_composer_effects_must_exist_in_library(settings: Settings, configs_dir: Path) -> None:
    p = configs_dir / "composer" / "pilot_v1.yaml"
    p.write_text(p.read_text().replace("effect: rights_enforcement_effectiveness", "effect: magic_rights"))
    with pytest.raises(ConfigurationError, match="magic_rights"):
        submit(configs_dir / "runs" / "synthetic_pilot.yaml", settings)
