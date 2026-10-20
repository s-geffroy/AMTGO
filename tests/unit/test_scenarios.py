"""M6 : scénarios S1/S2A/S2C, garde-fous de déplacement, décomposition S2A, diagnostic S2C."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from amtgo.config.loader import load_model
from amtgo.core.channels import IntegChannel
from amtgo.errors import InsufficientEvidence, NormativeViolation
from amtgo.fragmentation.engine import fragmentation
from amtgo.identity.state import SocialState
from amtgo.integration.engine import integration
from amtgo.scenarios.coercion import CoercionDependencyDiagnostic, coercion_dependency
from amtgo.scenarios.decomposition import decompose_voluntary_effect
from amtgo.scenarios.model import (
    MobilityRegime,
    Scenario,
    assert_no_induced_displacement,
    draw_scenario,
)
from amtgo.scenarios.projection import project_population
from amtgo.validation import worlds as W

CONFIGS = Path(__file__).resolve().parents[2] / "configs"


def _raw(name: str = "s1_baseline") -> dict[str, Any]:
    return dict(yaml.safe_load((CONFIGS / "scenarios" / f"{name}.yaml").read_text()))


def _scenario(name: str = "s1_baseline") -> Scenario:
    return load_model(Scenario, CONFIGS / "scenarios" / f"{name}.yaml")


def test_all_configured_scenarios_load() -> None:
    regimes = {_scenario(p.stem).mobility_regime for p in (CONFIGS / "scenarios").glob("*.yaml")}
    assert regimes == set(MobilityRegime)


@pytest.mark.parametrize("field", ["forced_migration", "reform_induced_relocation"])
@pytest.mark.parametrize("name", ["s1_baseline", "s2a_voluntary", "s2c_diagnostic"])
def test_displacement_is_never_a_parameter(name: str, field: str) -> None:
    raw = _raw(name)
    raw["migration"][field] = 1000.0
    with pytest.raises(ValidationError, match=field):
        Scenario.model_validate(raw)


@pytest.mark.parametrize("name", ["s1_baseline", "s2c_diagnostic"])
def test_reform_mobility_response_only_in_s2a(name: str) -> None:
    raw = _raw(name)
    raw["migration"]["voluntary_response"] = "causal:mobility_v1"
    with pytest.raises(ValidationError):
        Scenario.model_validate(raw)
    raw = _raw("s2a_voluntary")
    raw["migration"]["voluntary_response"] = "causal:mobility_v1"
    assert Scenario.model_validate(raw).migration.voluntary_response


def test_no_single_climate_scenario() -> None:
    raw = _raw()
    raw["climate"]["pathways"] = {"only": {"lo": 1.0, "hi": 1.1}}
    with pytest.raises(ValidationError, match="deux trajectoires"):
        Scenario.model_validate(raw)


def test_inverted_interval_refused() -> None:
    raw = _raw()
    raw["economy"]["annual_fiscal_base_growth"] = {"lo": 0.03, "hi": 0.0}
    with pytest.raises(ValidationError):
        Scenario.model_validate(raw)


def test_draws_are_reproducible() -> None:
    sc = _scenario()
    a, b, c = draw_scenario(sc, 50, 0), draw_scenario(sc, 50, 0), draw_scenario(sc, 50, 1)
    assert np.array_equal(a.population, b.population) and np.array_equal(a.climate, b.climate)  # type: ignore[arg-type]
    assert not np.array_equal(a.population, c.population)
    lo, hi = (1.02 * 0.998) ** 10, (1.03 * 1.002) ** 10
    assert np.all((a.population >= lo - 1e-12) & (a.population <= hi + 1e-12))


def test_s1_projection_moves_nobody() -> None:
    sc = _scenario()
    base = np.random.default_rng(0).uniform(10, 1000, (30, 40))
    proj = project_population(base, sc, draw_scenario(sc, 30, 0))
    assert proj.forced_migration == 0.0 and proj.reform_induced_relocation == 0.0
    assert proj.voluntary_response == "none"
    shares = proj.samples / proj.samples.sum(axis=1, keepdims=True)
    assert np.allclose(shares, base / base.sum(axis=1, keepdims=True))


def test_s2a_response_unknown_without_causal_library() -> None:
    sc = _scenario("s2a_voluntary")
    proj = project_population(np.ones((5, 3)), sc, draw_scenario(sc, 5, 0))
    assert proj.voluntary_response == "CAUSAL_EFFECT_UNKNOWN"


def test_s2c_never_projects_population() -> None:
    sc = _scenario("s2c_diagnostic")
    with pytest.raises(NormativeViolation, match="S2C"):
        project_population(np.ones((5, 3)), sc, draw_scenario(sc, 5, 0))


def test_runtime_guard() -> None:
    sc = _scenario()
    with pytest.raises(NormativeViolation):
        assert_no_induced_displacement(sc, forced=1.0, induced=0.0)
    with pytest.raises(NormativeViolation):
        assert_no_induced_displacement(sc, forced=0.0, induced=0.01)
    with pytest.raises(NormativeViolation):
        assert_no_induced_displacement(sc, forced=0.0, induced=None)


def test_dfi_invariant_under_uniform_growth() -> None:
    """Sous S1, une croissance uniforme ne change ni F ni J_conn (rapports homogènes de degré 0)."""
    w = W.world_b()
    p = w.probes["split"]
    scaled = SocialState(w.state.ontology_id, w.state.cell_ids, w.state.groups, w.state.population * 1.37,
                         ties=w.state.ties, exposure=w.state.exposure, quality=w.state.quality)
    weights = {c: 1.0 for c in IntegChannel}
    f0 = [(f.group, f.channel, None if f.value is None else f.value.mean) for f in fragmentation(w.state, p)]
    f1 = [(f.group, f.channel, None if f.value is None else f.value.mean) for f in fragmentation(scaled, p)]
    for a, b in zip(f0, f1, strict=True):
        assert a[:2] == b[:2] and (a[2] == b[2] or a[2] == pytest.approx(b[2]))
    j0, j1 = integration(w.state, p, weights).j_conn, integration(scaled, p, weights).j_conn
    assert j0 is not None and j1 is not None and j0.mean == pytest.approx(j1.mean)


# --- S2A : décomposition ----------------------------------------------------------


def _outcome(partition: float, n: np.ndarray) -> np.ndarray:
    """Résultat jouet non linéaire : dépend de la partition et de la répartition."""
    return np.asarray(partition * (n[:, 0] ** 2) / n.sum(axis=1) + n[:, 2] * 0.1)


def test_decomposition_sums_to_total() -> None:
    rng = np.random.default_rng(1)
    n0 = rng.uniform(10, 100, (20, 4))
    flow = rng.uniform(-5, 5, (20, 4))
    flow -= flow.mean(axis=1, keepdims=True)
    n1 = n0 + flow
    d = decompose_voluntary_effect(_outcome, 1.0, 1.5, n0, n1, np.array([True, True, False, False]),
                                   response_source="causal:test")
    assert d.status == "DECOMPOSED"
    assert d.composition is not None and d.spillover is not None and d.total is not None
    assert d.direct.mean + d.composition.mean + d.spillover.mean == pytest.approx(d.total.mean)


def test_decomposition_unknown_response_is_not_zero() -> None:
    n0 = np.ones((10, 4))
    d = decompose_voluntary_effect(_outcome, 1.0, 2.0, n0, None, np.ones(4, dtype=bool))
    assert d.status == "CAUSAL_EFFECT_UNKNOWN"
    assert d.composition is None and d.spillover is None and d.total is None


def test_decomposition_requires_voluntary_source_and_conservation() -> None:
    n0 = np.ones((10, 4))
    with pytest.raises(ValueError, match="source"):
        decompose_voluntary_effect(_outcome, 1.0, 2.0, n0, n0, np.ones(4, dtype=bool))
    with pytest.raises(ValueError, match="conserve"):
        decompose_voluntary_effect(_outcome, 1.0, 2.0, n0, n0 * 1.1, np.ones(4, dtype=bool), "causal:x")


# --- S2C : diagnostic agrégé ------------------------------------------------------


def test_coercion_dependency_known_case() -> None:
    feasible = np.tile(np.array([[50.0, 50.0], [50.0, 50.0]]), (10, 1, 1))
    implied = np.tile(np.array([[100.0, 0.0], [0.0, 100.0]]), (10, 1, 1))
    d = coercion_dependency(feasible, implied, np.full(10, 0.2), np.full(10, 1.0), "I7")
    assert d.aggregate_population_equivalent.mean == pytest.approx(100.0)
    assert d.apparent_homogeneity_gain.mean == pytest.approx(0.5)
    assert d.ratio.mean == pytest.approx(0.8)


def test_coercion_identical_distributions_is_zero() -> None:
    c = np.random.default_rng(0).uniform(1, 10, (8, 3, 2))
    d = coercion_dependency(c, c.copy(), np.ones(8), np.ones(8), "I7")
    assert d.aggregate_population_equivalent.mean == pytest.approx(0.0)
    assert d.ratio.mean == pytest.approx(0.0)


def test_coercion_rejects_cell_level_or_inconsistent_input() -> None:
    with pytest.raises(ValueError):
        coercion_dependency(np.ones((5, 4)), np.ones((5, 4)), np.ones(5), np.ones(5), "I7")
    a = np.ones((5, 2, 2))
    b = a.copy()
    b[:, 0, 0] += 3.0  # population d'un groupe non conservée
    with pytest.raises(ValueError, match="conserver"):
        coercion_dependency(a, b, np.ones(5), np.ones(5), "I7")
    with pytest.raises(InsufficientEvidence):
        coercion_dependency(a, a, np.zeros(5), np.zeros(5), "I7")


def test_coercion_output_is_aggregate_only() -> None:
    a = np.tile(np.array([[3.0, 1.0], [1.0, 3.0]]), (6, 1, 1))
    b = np.tile(np.array([[4.0, 0.0], [0.0, 4.0]]), (6, 1, 1))
    out = coercion_dependency(a, b, np.full(6, 0.5), np.full(6, 1.0), "I7").to_aggregate_dict()
    assert set(out) == {"aggregate_population_equivalent", "apparent_homogeneity_gain", "ratio", "confidence"}
    for v in out.values():
        assert not isinstance(v, dict) or set(v) == {"mean", "lower", "upper"}
    assert CoercionDependencyDiagnostic.__dataclass_fields__.keys() == {
        "aggregate_population_equivalent", "apparent_homogeneity_gain", "ratio", "confidence"}
