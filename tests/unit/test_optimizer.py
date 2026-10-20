"""M10 : agrégation robuste, ε-dominance, infaisabilité, objectifs, benchmark exact."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError
from scipy import sparse

from amtgo.institutions.regimes import load_regime
from amtgo.manifests.normative import RobustnessWeights
from amtgo.optimization import benchmark
from amtgo.optimization.manifest import OptimizerManifest
from amtgo.optimization.objectives import functional_cut, institutional_cost, transition_share
from amtgo.optimization.pareto import Solution, eps_dominates, infeasibility_certificate, nondominated_sort, robust

EPS = {"a": 0.1, "b": 0.1}


def test_robust_aggregation() -> None:
    w = RobustnessWeights(cvar_alpha=0.5, lambda_tail=1.0, lambda_var=0.0)
    assert robust([1.0, 2.0, 3.0, 4.0], w) == pytest.approx(2.5 + 3.5)  # moyenne + moyenne de la moitié haute
    assert robust([2.0], RobustnessWeights(cvar_alpha=0.9, lambda_tail=0.0, lambda_var=0.0)) == 2.0


def test_eps_dominance() -> None:
    assert eps_dominates({"a": 0.0, "b": 0.0}, {"a": 0.5, "b": 0.0}, EPS)
    assert not eps_dominates({"a": 0.0, "b": 0.0}, {"a": 0.05, "b": 0.0}, EPS)  # sous la résolution
    assert not eps_dominates({"a": 0.0, "b": 0.5}, {"a": 0.5, "b": 0.0}, EPS)  # compromis
    # Un objectif inconnu n'est jamais compté : seuls les objectifs connus des deux départagent.
    assert eps_dominates({"a": 0.0, "b": None}, {"a": 0.5, "b": 0.0}, EPS)
    assert not eps_dominates({"a": None, "b": None}, {"a": 0.5, "b": 0.5}, EPS)


def test_nondominated_sort_and_infeasible_unranked() -> None:
    sols = [Solution("x", "f", {}, {"a": 0.0, "b": 1.0}, True), Solution("y", "f", {}, {"a": 1.0, "b": 0.0}, True),
            Solution("z", "f", {}, {"a": 1.0, "b": 1.0}, True), Solution("w", "f", {}, {"a": 0.0, "b": 0.0}, False)]
    nondominated_sort(sols, EPS)
    assert [s.rank for s in sols] == [1, 1, 2, None]


def test_infeasibility_certificate_never_relaxes() -> None:
    sols = [Solution("x", "f", {}, {}, False, ["droits:g|land", "droits:h|land"]),
            Solution("y", "f", {}, {}, False, ["droits:g|land"])]
    c = infeasibility_certificate(sols, {"tau": 0.5})
    assert c is not None and c["status"] == "INFEASIBLE" and c["relaxation_applied"] is False
    assert c["binding_constraints"]["droits:g|land"] == 2
    assert c["minimal_conflict_sets"] == [["droits:g|land"]]
    assert infeasibility_certificate([Solution("ok", "f", {}, {}, True)], {}) is None


def test_union_cuts_nothing_and_transition_is_label_free() -> None:
    k = sparse.csr_matrix(np.ones((4, 4)))
    assert functional_cut(k, np.ones(4), np.zeros(4, dtype=int)) == 0.0
    assert functional_cut(k, np.ones(4), np.array([0, 0, 1, 1])) > 0
    a = np.array([0, 0, 1, 1])
    assert transition_share(1 - a, a, np.ones(4)) == pytest.approx(0.0)  # renommer n'est pas transiter
    assert transition_share(np.array([0, 1, 1, 1]), a, np.ones(4)) == pytest.approx(0.25)


def test_no_abstract_state_count_penalty() -> None:
    """Sans coûts réels (fixes, frontières), le nombre d'États ne coûte rien (prompt §42)."""
    from pathlib import Path

    r0 = load_regime(Path(__file__).resolve().parents[2] / "configs", "R0_CURRENT_LIKE")
    assert {institutional_cost(n, r0, 0.0, 0.0, 0.0, 0.0) for n in (1, 2, 5, 20)} == {0.0}
    assert institutional_cost(3, r0, 1.0, 1.0, 0.0, 0.0) > institutional_cost(2, r0, 1.0, 1.0, 0.0, 0.0)


def test_manifest_epsilon_covers_known_objectives_only() -> None:
    base = {"optimizer_id": "o", "version": "1", "description": "d", "border_cost_per_km": 0.0,
            "benchmark_tolerance": 0.05,
            "epsilon": {k: 0.01 for k in ("J_D", "J_F", "J_conn", "J_V", "J_G", "J_T", "J_inst", "J_reif")}}
    OptimizerManifest.model_validate(base)
    with pytest.raises(ValidationError):  # J_R est UNKNOWN : pas de résolution déclarable
        OptimizerManifest.model_validate({**base, "epsilon": {**base["epsilon"], "J_R": 0.1}})


def test_exact_benchmark() -> None:
    r = benchmark.run()
    assert r["partitions_enumerated"] == len(benchmark.contiguous_bipartitions())
    assert r["kmeans"]["best_gap"] <= 0.05 and r["spectral"]["best_gap"] <= 0.05
    assert min(r["kmeans"]["relative_gaps"]) == pytest.approx(0.0, abs=1e-9)  # optimum exact atteint
    # Goodhart « micro-territoires » : la coupe seule a pour front des États d'une cellule.
    assert set(r["cut_only_front"]["smallest_state_cells"]) == {1}
