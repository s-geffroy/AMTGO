"""M7 : enregistrements causaux, admissibilité, nouveauté, gel, DiD échelonné, transport."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from amtgo.causal.did import NEVER, Panel, estimate
from amtgo.causal.library import CausalAnswer, FrozenCausalLibrary, NoveltyRules, library_hash
from amtgo.causal.model import (
    CAUSAL_EFFECT_UNKNOWN,
    Admissibility,
    CausalEffect,
    Diagnostic,
    TransportStatus,
    Treatment,
    sovereignty_residual,
    support_distance,
)
from amtgo.causal.transport import overlap, transport_status
from amtgo.core.uncertainty import UncertainValue
from amtgo.data.synthetic_world import PanelDesign, SyntheticWorld, panel_true_att, simulate_panel
from amtgo.errors import ConfigurationError, ReproducibilityError
from amtgo.scenarios.model import Interval

DID_DIAG = {d: Diagnostic.PASSED for d in ("pre_trends", "anticipation", "composition", "spillovers",
                                           "endogenous_adoption")}


def _effect(**kw: Any) -> CausalEffect:
    base: dict[str, Any] = dict(
        effect_key="eff", treatment={"component": "fisc", "definition": "d", "intensity_support": {"lo": 0, "hi": 1}},
        outcome={"kind": "V", "variable": "v", "unit": "u"}, source_context="s", target_context="t",
        estimand="ATT", design="staggered_did", grade="I3",
        effect=UncertainValue.from_samples(np.linspace(0.05, 0.1, 50)), time_horizon_years=5,
        spillover_model="none", mechanism="m", transport_status="IDENTIFIED", overlap=0.95,
        diagnostics=DID_DIAG, source_ids=("src",))
    base.update(kw)
    return CausalEffect.model_validate(base)


def test_grade_cannot_exceed_design_ceiling() -> None:
    with pytest.raises(ValidationError, match="plafond"):
        _effect(grade="I1")


def test_strong_grade_requires_passed_diagnostics() -> None:
    with pytest.raises(ValidationError, match="diagnostics"):
        _effect(diagnostics={})
    failed = _effect(diagnostics={**DID_DIAG, "pre_trends": Diagnostic.FAILED})
    assert failed.admissibility(0.2) is Admissibility.UNSUPPORTED  # conservé, jamais utilisé


def test_expert_hypothesis_is_bounds_only_and_never_fact() -> None:
    with pytest.raises(ValidationError, match="bornes"):
        _effect(design="expert_hypothesis", grade="I7", diagnostics={})
    e = _effect(design="expert_hypothesis", grade="I7", diagnostics={}, effect=UncertainValue.bounds(0.0, 0.3))
    assert e.admissibility(0.2) is Admissibility.EXPLORATORY_ONLY


@settings(max_examples=40, deadline=None)
@given(st.sampled_from(list(TransportStatus)), st.floats(0.0, 1.0))
def test_i7_never_becomes_a_causal_fact(transport: TransportStatus, ov: float) -> None:
    e = _effect(design="expert_hypothesis", grade="I7", diagnostics={}, effect=UncertainValue.bounds(0.0, 0.3),
                transport_status=transport, overlap=ov)
    assert e.admissibility(0.2) is not Admissibility.CAUSAL_FACT


def test_admissibility_matrix() -> None:
    assert _effect().admissibility(0.2) is Admissibility.CAUSAL_FACT
    assert _effect(transport_status="PARTIAL", overlap=0.5,
                   effect=UncertainValue.bounds(0.0, 0.2)).admissibility(0.2) is Admissibility.BOUNDED
    assert _effect(overlap=0.1).admissibility(0.2) is Admissibility.UNSUPPORTED
    assert _effect(transport_status="UNSUPPORTED").admissibility(0.2) is Admissibility.UNSUPPORTED
    assert _effect(design="partial_identification", grade="I6", diagnostics={},
                   effect=UncertainValue.bounds(0.0, 0.2)).admissibility(0.2) is Admissibility.BOUNDED


@pytest.mark.parametrize("label", ["autonomy", "federalism"])
def test_labels_are_not_primitive_treatments(label: str) -> None:
    with pytest.raises(ValidationError):
        Treatment.model_validate({"component": label, "definition": "d", "intensity_support": {"lo": 0, "hi": 1}})


def test_sovereignty_is_a_decomposed_bundle() -> None:
    with pytest.raises(ValidationError, match="bundle"):
        Treatment.model_validate({"component": "sovereignty", "definition": "d",
                                  "intensity_support": {"lo": 0, "hi": 1}})
    total = np.full(100, 1.0)
    res = sovereignty_residual(total, [np.full(100, 0.3), np.full(100, 0.5)], np.full(100, 0.1))
    assert res.mean == pytest.approx(0.1)


def test_support_distance() -> None:
    iv = Interval(lo=0.2, hi=0.6)
    assert support_distance(0.4, iv) == 0.0
    assert support_distance(0.8, iv) == pytest.approx(0.5)
    assert support_distance(0.0, iv) == pytest.approx(0.5)


def _frozen(effects: list[CausalEffect]) -> FrozenCausalLibrary:
    return FrozenCausalLibrary(effects, library_hash(effects), 0.2, NoveltyRules(kappa=1.0, max_distance=0.5))


def test_frozen_library_queries() -> None:
    lib = _frozen([_effect()])
    assert lib.query("eff", "t").status == "CAUSAL_FACT"
    assert lib.query("absent", "t").status == CAUSAL_EFFECT_UNKNOWN
    wrong = lib.query("eff", "elsewhere")
    assert wrong.status == CAUSAL_EFFECT_UNKNOWN and "τ_T" in wrong.reason  # transport jamais présumé
    near = lib.query("eff", "t", intensity=1.2)  # d_A = 0,2 : bornes élargies, plus un fait
    assert near.status == "BOUNDED" and near.effect is not None and not near.effect.has_samples
    assert lib.query("eff", "t", intensity=2.0).status == CAUSAL_EFFECT_UNKNOWN  # d_A = 1 > 0,5


def test_frozen_library_detects_tampering_and_is_read_only() -> None:
    e = _effect()
    with pytest.raises(ReproducibilityError):
        FrozenCausalLibrary([e.model_copy(update={"overlap": 0.99})], library_hash([e]), 0.2,
                            NoveltyRules(kappa=1.0, max_distance=0.5))
    lib = _frozen([e])
    with pytest.raises(ValidationError):
        lib.record("eff").overlap = 0.1  # type: ignore[misc]


def test_answer_draws_and_unknown() -> None:
    rng = np.random.default_rng(0)
    a = CausalAnswer("e", "CAUSAL_FACT", UncertainValue.from_samples([1.0, 2.0, 3.0]), None, "")
    assert set(a.draws(50, rng)) <= {1.0, 2.0, 3.0}
    b = CausalAnswer("e", "EXPLORATORY_ONLY", UncertainValue.bounds(0.0, 0.3), None, "")
    assert np.all((b.draws(50, rng) >= 0) & (b.draws(50, rng) <= 0.3))
    with pytest.raises(ConfigurationError, match=CAUSAL_EFFECT_UNKNOWN):
        CausalAnswer("e", CAUSAL_EFFECT_UNKNOWN, None, None, "absent").interval()


# --- DiD sur panels synthétiques à vérité connue -----------------------------------

WORLD = SyntheticWorld.from_params(dict(seed=20251020, bbox=[-25, -26, -21, -22], background_density=5, n_towns=25,
                                        town_peak_density=[50, 800], town_scale_km=[3, 15], quadrature_km=2.0))


def _design(adoption: str) -> PanelDesign:
    return PanelDesign.from_params(dict(
        bbox=[-35, -36, -31, -32], districts_x=6, districts_y=6, first_year=2010, last_year=2024,
        cohorts=[2015, 2018], att=0.08, ramp_years=3, noise_sd=0.02, adoption=adoption,
        endogenous_pre_slope=0.015, density_log_mean=3.0, density_log_sd=0.9))


def _panel(adoption: str, exposure: np.ndarray | None = None) -> tuple[Panel, np.ndarray, float]:
    d = _design(adoption)
    ds = simulate_panel(WORLD, d)
    cohort = np.array([x.cohort for x in ds])
    return (Panel(np.array([x.outcome for x in ds]), d.years, cohort, exposure),
            np.array([x.negative_control for x in ds]), panel_true_att(d, list(cohort)))


def test_did_recovers_exogenous_effect() -> None:
    panel, nc, truth = _panel("exogenous")
    r = estimate(panel, 200, 0, 0.05, negative_control=nc)
    assert r.att.lower is not None and r.att.upper is not None
    assert r.att.lower <= truth <= r.att.upper
    assert r.diagnostics["pre_trends"] is Diagnostic.PASSED
    assert r.robustness["placebo"] == "PASSED" and r.robustness["negative_control"] == "PASSED"


def test_did_flags_endogenous_adoption() -> None:
    panel, nc, truth = _panel("endogenous")
    r = estimate(panel, 200, 0, 0.05, negative_control=nc)
    assert r.diagnostics["pre_trends"] is Diagnostic.FAILED
    assert r.diagnostics["endogenous_adoption"] is Diagnostic.FAILED
    assert r.att.lower is not None and r.att.lower > truth  # biaisé : la règle de rejet est nécessaire


def test_did_detects_spillovers_on_controls() -> None:
    panel, _, _ = _panel("exogenous")
    rng = np.random.default_rng(3)
    exposure = rng.uniform(0, 1, len(panel.cohort))
    y = panel.y.copy()
    ctrl = panel.cohort == NEVER
    y[ctrl] += 0.15 * exposure[ctrl, None] * (panel.years >= 2015)[None, :]  # contagion aux voisins
    r = estimate(Panel(y, panel.years, panel.cohort, exposure), 200, 0, 0.05)
    assert r.diagnostics["spillovers"] is Diagnostic.FAILED
    clean = estimate(Panel(panel.y, panel.years, panel.cohort, exposure), 200, 0, 0.05)
    assert clean.diagnostics["spillovers"] is Diagnostic.PASSED


def test_did_requires_never_treated_controls() -> None:
    panel, _, _ = _panel("exogenous")
    cohort = np.where(panel.cohort == NEVER, 2020, panel.cohort)
    with pytest.raises(ValueError, match="témoins"):
        estimate(Panel(panel.y, panel.years, cohort), 50, 0, 0.05)


def test_overlap_and_transport_status() -> None:
    s = np.linspace(1, 100, 200)
    assert overlap({"density": s}, {"density": np.array([20.0, 50.0])}) == 1.0
    assert overlap({"density": s}, {"density": np.array([500.0, 900.0])}) == 0.0
    assert overlap({"density": s}, {}) == 0.0  # modificateur absent : jamais supposé identique
    assert transport_status(0.95, 0.9, 0.2) is TransportStatus.IDENTIFIED
    assert transport_status(0.5, 0.9, 0.2) is TransportStatus.PARTIAL
    assert transport_status(0.1, 0.9, 0.2) is TransportStatus.UNSUPPORTED
