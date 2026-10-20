"""M5 : moteurs D/F/I — formules, bornes, canaux inconnus, règles de décision."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy import sparse

from amtgo.core.channels import FragChannel, IntegChannel
from amtgo.core.enums import PrivacyClass
from amtgo.domination.engine import domination
from amtgo.errors import CausalUnsupported
from amtgo.fragmentation.engine import fragmentation
from amtgo.geo.partition import BorderDim, BorderVector, Partition, PartitionLevel
from amtgo.identity.reification import alignment, reification_risk
from amtgo.identity.state import BoundedSalienceResponse, SocialState, StaticIdentity
from amtgo.infrastructure.hyperedges import Hyperedge, HyperedgeType
from amtgo.institutions.competences import CompetenceVector, DecisionRule, Domain, check_exclusive
from amtgo.integration.engine import integration
from amtgo.manifests.normative import RightsThresholds
from amtgo.validation import worlds as W

RIGHTS = RightsThresholds(severe_domination_threshold=0.5, severe_domination_probability_max=0.05,
                          urgent_domination_threshold=0.7, urgent_probability=0.5)


def _state(pop: np.ndarray, kernel: sparse.csr_matrix, **kw: object) -> SocialState:
    ids = [f"c{i}" for i in range(pop.shape[1])]
    return SocialState("o", ids, [f"g{k}" for k in range(pop.shape[2])], pop, ties={FragChannel.NETWORK: kernel},
                       exposure={IntegChannel.SPATIAL: kernel},
                       quality={IntegChannel.SPATIAL: np.ones((pop.shape[2], pop.shape[2]))}, **kw)  # type: ignore[arg-type]


def _part(assign: list[int], border: BorderVector = W.HARD) -> Partition:
    k = max(assign) + 1
    return Partition("m", [f"c{i}" for i in range(len(assign))],
                     [PartitionLevel("state", np.array(assign), [f"s{j}" for j in range(k)], border)])


def test_decision_rule_power() -> None:
    r = DecisionRule(threshold=0.5)
    assert r.power("g", 0.25) == pytest.approx(0.5)
    assert r.power("g", 0.6) == 1.0
    assert DecisionRule(threshold=2 / 3).power("g", 0.25) == pytest.approx(0.75)
    assert DecisionRule(threshold=0.5, veto_groups=("g",)).power("g", 0.0) == 1.0


def test_exclusive_competences_sum_to_one() -> None:
    a = CompetenceVector(authority={Domain.SECURITY: 0.7})
    b = CompetenceVector(authority={Domain.SECURITY: 0.3})
    check_exclusive([a, b], [Domain.SECURITY])
    with pytest.raises(ValueError):
        check_exclusive([a, a], [Domain.SECURITY])


def test_no_border_no_fragmentation() -> None:
    lat = W.Lattice(6, 3)
    st_ = _state(np.full((10, lat.n, 2), 50.0), lat.distance_kernel())
    for f in fragmentation(st_, _part([0] * lat.n)):
        assert f.value is None or f.value.mean == 0.0
    assert integration(st_, _part([0] * lat.n), {IntegChannel.SPATIAL: 1.0}).j_conn.mean == 0.0  # type: ignore[union-attr]


def test_unknown_channels_are_unknown_not_zero() -> None:
    lat = W.Lattice(4, 2)
    st_ = _state(np.full((10, lat.n, 1), 10.0), lat.distance_kernel())
    by = {(f.channel, f.group): f.value for f in fragmentation(st_, _part([0, 0, 1, 1] * 2))}
    assert by[(FragChannel.MOBILITY, "g0")] is None
    assert by[(FragChannel.TERRITORIAL, "g0")] is None
    assert by[(FragChannel.NETWORK, "g0")] is not None
    res = integration(st_, _part([0, 0, 1, 1] * 2), {IntegChannel.SPATIAL: 1.0})
    assert IntegChannel.FAMILY in res.unknown_channels


def test_full_mitigation_cancels_cut() -> None:
    lat = W.Lattice(6, 2)
    st_ = _state(np.full((10, lat.n, 1), 30.0), lat.distance_kernel())
    p = lat.bands([3])
    full = Hyperedge(hyperedge_id="h", type=HyperedgeType.RIVER, members=tuple(lat.ids),
                     mitigation={FragChannel.NETWORK: 1.0})
    f = {(x.channel, x.group): x.value for x in fragmentation(st_, p, [full])}
    assert f[(FragChannel.NETWORK, "g0")].mean == pytest.approx(0.0)  # type: ignore[union-attr]


@settings(max_examples=25, deadline=None)
@given(st.floats(min_value=0.0, max_value=1.0), st.floats(min_value=0.0, max_value=1.0))
def test_fragmentation_bounded_and_monotone_in_sigma(s1: float, s2: float) -> None:
    lat = W.Lattice(6, 2)
    st_ = _state(np.full((5, lat.n, 1), 20.0), lat.distance_kernel())
    lo, hi = sorted((s1, s2))
    vals = []
    for s in (lo, hi):
        f = fragmentation(st_, lat.bands([3], b=W.border(M=s)))
        vals.append(next(x.value.mean for x in f if x.channel is FragChannel.NETWORK))  # type: ignore[union-attr]
    assert 0.0 <= vals[0] <= vals[1] <= 1.0


def test_domination_formula_and_absent_groups() -> None:
    w = W.world_e()
    est = domination(w.state, w.probes["inclusive"], w.institutions["inclusive"], RIGHTS)
    n = next(d for d in est if d.group == "n" and d.domain is Domain.EXECUTIVE_POWER)
    # n ≈ 30 % sous majorité simple : pouvoir 0,6 → X 0,4 ; garde-fous 0,5 → D_pot ≈ 0,2.
    assert n.potential.mean == pytest.approx(0.2, abs=0.02)
    assert n.realized is None  # aucune observation : UNKNOWN, jamais 0


def test_urgent_flag() -> None:
    w = W.world_e()
    est = domination(w.state, w.probes["excluded"], w.institutions["excluded"], RIGHTS)
    m = next(d for d in est if d.group == "m" and d.domain is Domain.EXECUTIVE_POWER)
    assert m.violation and m.urgent  # D_pot 0,8 > τ_urgent 0,7


def test_alignment_bounds() -> None:
    w = W.world_a()
    split = alignment(w.state, w.probes["split"]).mean
    unified = alignment(w.state, w.probes["unified"]).mean
    assert unified == pytest.approx(0.0) and 0.9 < split <= 1.0  # type: ignore[operator]


def test_reification_unknown_without_causal_support() -> None:
    w = W.world_a()
    r = reification_risk(w.state, w.probes["split"], w.probes["unified"], 10, StaticIdentity())
    assert r["rri"] is None and r["status"].startswith("CAUSAL_EFFECT_UNKNOWN")
    with pytest.raises(CausalUnsupported):
        StaticIdentity().salience_response(0.5, 10)
    b = reification_risk(w.state, w.probes["split"], w.probes["unified"], 10,
                         BoundedSalienceResponse(0.0, 0.5, 10, "hypothèse I7"))
    assert b["status"] == "BOUNDED" and b["rri"].mean is None  # intervalle, jamais un point
    assert b["rri"].upper > 0


def test_social_state_refuses_public_class() -> None:
    lat = W.Lattice(2, 2)
    with pytest.raises(ValueError):
        _state(np.ones((2, lat.n, 1)), lat.distance_kernel(), privacy_class=PrivacyClass.PUBLIC)


def test_border_vector_complete() -> None:
    with pytest.raises(ValueError):
        BorderVector(strength={BorderDim.POLITICAL: 1.0})
