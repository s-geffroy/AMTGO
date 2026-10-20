"""M6 : régimes typés, transferts neutres, viabilité conditionnelle, monde V."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from amtgo.institutions.regimes import ConstitutionalRegime, RegimeId, load_regime
from amtgo.institutions.viability import (
    Territory,
    ViabilityContext,
    ViabilityStatus,
    compute_viability,
    draw_model,
    union_transfers,
)
from amtgo.manifests.normative import ViabilityThresholds
from amtgo.validation import viability_worlds as V

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
THRESHOLDS = ViabilityThresholds(service_coverage_min=1.0, shortfall_probability_max=0.1)
REGIMES = {r.value: load_regime(CONFIGS, r.value) for r in RegimeId}


def test_border_dimensions_derive_from_rules() -> None:
    r1 = REGIMES["R1_COMMON_MARKET"]
    assert r1.border_template == {"P": 1.0, "C": 0.4, "E": 0.2, "M": 0.1, "R": 0.8, "S": 0.9}


def test_derived_dimensions_cannot_be_declared() -> None:
    raw = yaml.safe_load((CONFIGS / "regimes" / "R3_FEDERAL_CONTINENTAL.yaml").read_text())
    raw["declared_border"]["E"] = 0.9  # marché commun complet ET frontière économique forte
    with pytest.raises(ValidationError):
        ConstitutionalRegime.model_validate(raw)


def test_regimes_integrate_monotonically() -> None:
    """R0 → R3 : chaque régime abaisse (ou garde) les frontières économique, de mobilité et de sécurité."""
    order = [REGIMES[r.value].border_template for r in RegimeId]
    for dim in ("E", "M", "S", "R"):
        values = [b[dim] for b in order]
        assert values == sorted(values, reverse=True), dim


@settings(max_examples=50, deadline=None)
@given(st.lists(st.floats(1e3, 1e7), min_size=2, max_size=6), st.sampled_from(list(REGIMES)))
def test_transfers_are_budget_neutral(pops: list[float], rid: str) -> None:
    rng = np.random.default_rng(len(pops))
    pop = np.array([pops] * 3)
    revenue = pop * rng.uniform(50, 400, pop.shape)
    t = union_transfers(revenue, pop, REGIMES[rid])
    assert np.allclose(t.sum(axis=1), 0.0, atol=1e-6 * revenue.sum())


def test_transfers_help_the_poorer_territory() -> None:
    pop = np.array([[1e6, 1e6]])
    t = union_transfers(np.array([[3e8, 1e8]]), pop, REGIMES["R3_FEDERAL_CONTINENTAL"])
    assert t[0, 1] > 0 > t[0, 0]
    assert np.all(union_transfers(np.array([[3e8, 1e8]]), pop, REGIMES["R0_CURRENT_LIKE"]) == 0)


def test_world_v_properties_hold() -> None:
    res = V.evaluate(REGIMES, "R0_CURRENT_LIKE", THRESHOLDS)
    failed = [(t, v) for t, ok, v in V.checks(res, "R0_CURRENT_LIKE") if not ok]
    assert not failed, failed


def _context(union: object = None) -> tuple[ViabilityContext, object]:
    sc = V.neutral_scenario()
    model = V.world_model("R0_CURRENT_LIKE")
    effects = V.world_effects()
    exploratory, overhead = draw_model(model, effects, V.DRAWS, 0)
    from amtgo.scenarios.model import draw_scenario

    return ViabilityContext(union, model, REGIMES["R0_CURRENT_LIKE"], THRESHOLDS,  # type: ignore[arg-type]
                            draw_scenario(sc, V.DRAWS, 0), effects, exploratory, overhead), sc


def test_missing_fiscal_accounts_are_unknown_not_viable() -> None:
    ctx, sc = _context(None)
    a = compute_viability(Territory("x", "state"), REGIMES["R2_CONFEDERAL"], sc, ctx)  # type: ignore[arg-type]
    assert a.status is ViabilityStatus.UNKNOWN and a.coverage is None
    assert "UNKNOWN" in a.statement() and "R2_CONFEDERAL" in a.statement()


def test_assessment_has_no_truth_value_and_states_context() -> None:
    ctx, sc = _context(V.world_union())
    a = compute_viability(Territory("small_dense", "state"), REGIMES["R1_COMMON_MARKET"], sc, ctx)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="hors contexte"):
        bool(a)
    text = a.statement()
    assert "R1_COMMON_MARKET" in text and "world_v_neutral" in text and "transferts" in text


def test_s2c_scenario_has_no_viability() -> None:
    from amtgo.config.loader import load_model
    from amtgo.scenarios.model import Scenario

    ctx, _ = _context(V.world_union())
    s2c = load_model(Scenario, CONFIGS / "scenarios" / "s2c_diagnostic.yaml")
    with pytest.raises(ValueError, match="S2C"):
        compute_viability(Territory("small_dense", "state"), REGIMES["R0_CURRENT_LIKE"], s2c, ctx)


def test_no_size_threshold_in_normative_schema() -> None:
    with pytest.raises(ValidationError):
        ViabilityThresholds.model_validate({"service_coverage_min": 1.0, "shortfall_probability_max": 0.1,
                                            "min_population": 1_000_000})


def test_unknown_territory_refused() -> None:
    ctx, sc = _context(V.world_union())
    with pytest.raises(KeyError):
        compute_viability(Territory("atlantis", "state"), REGIMES["R0_CURRENT_LIKE"], sc, ctx)  # type: ignore[arg-type]


def test_unknown_effect_makes_viability_unknown_not_zero() -> None:
    """Sans effet identifié ni borne déclarée, la viabilité est UNKNOWN : l'effet n'est jamais pris nul."""
    from amtgo.causal.library import CausalAnswer

    ctx, sc = _context(V.world_union())
    unknown = (CausalAnswer("x", "CAUSAL_EFFECT_UNKNOWN", None, None, "absent"), ctx.effects[1])
    ctx2 = ViabilityContext(ctx.union, ctx.model, ctx.observed_regime, ctx.thresholds, ctx.draws, unknown,
                            ctx.exploratory, ctx.overhead)
    a = compute_viability(Territory("small_dense", "state"), REGIMES["R1_COMMON_MARKET"], sc, ctx2)  # type: ignore[arg-type]
    assert a.status is ViabilityStatus.UNKNOWN
