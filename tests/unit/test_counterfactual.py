"""M13 : Map-C-Shallow — retrait du privilège juridique, dominance bloquée par l'axiome, gate de phase 9."""

from __future__ import annotations

from typing import Any

import pytest

from amtgo.manifests.normative import RobustnessWeights
from amtgo.optimization.archive import Variant, build
from amtgo.optimization.counterfactual import legacy_premium, phase_gate, statement
from amtgo.optimization.objectives import LEGACY_OBJECTIVES, OBJECTIVES, SqRelation, objectives_for
from amtgo.optimization.pareto import Solution, nondominated_sort

ROB = RobustnessWeights(cvar_alpha=0.9, lambda_tail=1.0, lambda_var=0.0)
EPS = {k: 0.01 for k in OBJECTIVES if k not in ("J_R", "J_P")}


def _omega(**kw: Any) -> dict[tuple[str, str], dict[str, Any]]:
    w: dict[str, Any] = {k: 0.5 for k in OBJECTIVES}
    w.update({"J_R": None, "J_P": None, "violations": []}, **kw)
    return {("m", "o"): w}


def test_objectives_by_map_mode() -> None:
    assert objectives_for("R") == OBJECTIVES
    assert set(OBJECTIVES) - set(objectives_for("C_SHALLOW")) == set(LEGACY_OBJECTIVES) == {"J_T"}
    with pytest.raises(ValueError, match="Map-C-Deep"):
        objectives_for("C_DEEP")


def test_merge_cannot_push_status_quo_off_the_front() -> None:
    """Sans J_T, l'union fait mieux sur les connus ; J_P (fusion : NOT_BETTER) bloque la dominance."""
    sq = Variant("sq", "STATUS_QUO", {}, _omega(J_T=0.0), relation=SqRelation.EQUAL)
    union = Variant("u", "GEOGRAPHIC", {}, _omega(J_T=0.8, J_F=0.0, J_conn=0.0), relation=SqRelation.COARSENING)
    split = Variant("s", "GEOGRAPHIC", {}, _omega(J_T=0.3, J_F=0.2, J_inst=0.9), relation=SqRelation.CROSSING,
                    relations={"u": SqRelation.REFINEMENT})
    union.relations["s"] = SqRelation.COARSENING
    c = build([sq, union, split], EPS, ROB, {}, objectives_for("C_SHALLOW"))
    ranks = {s.key: s.rank for s in c.solutions}
    assert ranks["sq"] == 1 and ranks["u"] == 1
    assert ranks["s"] == 1  # l'union domine sur les connus, mais elle est une fusion de « s » : bloquée
    assert c.unresolved["u"]["J_P"] == "NOT_BETTER"
    # Sans l'axiome (inconnus ignorés), la fusion aurait exclu le statu quo : c'est le biais corrigé.
    plain = [Solution(v.key, v.family, {}, {k: x for k, x in s.objectives.items()}, True)
             for v, s in zip([sq, union, split], c.solutions, strict=False)]
    nondominated_sort(plain, {k: v for k, v in EPS.items() if k != "J_T"})
    assert {s.key: s.rank for s in plain}["sq"] == 2


def test_legacy_premium_and_phase_gate() -> None:
    p = legacy_premium(["sq", "a"], ["a", "b"], {"sq"})
    assert p == {"enter_without_legacy": ["b"], "leave_without_legacy": ["sq"], "baselines_leaving": ["sq"]}
    ok = {"M": "PASSED", "C": "PASSED", "O": "PASSED", "S": "PASSED", "R": "PASSED"}
    assert phase_gate(ok, [{"control": "x", "status": "PASSED"}])["status"] == "INTERPRETABLE"
    g = phase_gate({**ok, "M": "FAILED"}, [])
    assert g["status"] == "RESEARCH_ONLY" and g["unmet_gates"] == {"M": "FAILED"}
    assert not phase_gate(ok, [{"control": "x", "status": "FAILED"}])["met"]


def test_statement_is_contemporary_and_non_prescriptive() -> None:
    s = statement("R1", ["o"], "sha256:" + "a" * 64, None, "NOT_IDENTIFIABLE", True, ["2025-01-01"])
    assert s.startswith("Si les frontières actuelles n'avaient aucune priorité juridique")
    assert "non prescriptif" in s and "consentement politique externe" in s
    for word in ("devrait", "prouve", "recommand"):
        assert word not in s
