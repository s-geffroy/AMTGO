"""M12 : trajectoires de transition, pénalité 02 §26, urgence 02 §27, archive Map-R, formulation 06 §15."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from amtgo.causal.library import CausalAnswer
from amtgo.causal.model import CAUSAL_EFFECT_UNKNOWN, IdentificationGrade
from amtgo.core.uncertainty import UncertainValue
from amtgo.manifests.normative import RobustnessWeights, TransitionWeights
from amtgo.optimization.archive import Variant, build
from amtgo.optimization.objectives import OBJECTIVES, SqRelation
from amtgo.optimization.transition import (
    PATH_OBJECTIVE,
    ActionType,
    TransitionManifest,
    apply_urgency,
    conclusion,
    institutional_paths,
    statement,
    status_quo_path,
    step_uncertainty,
    territorial_path,
    voi_indicator,
)
from amtgo.validation import composer_worlds as CW

IOTA = {"no_change": 0.0, "rights_enforcement": 0.1, "institutional_reform": 0.2, "autonomy": 0.4,
        "federation": 0.6, "border_weakening": 0.6, "border_change": 0.9, "sovereignty": 1.0}
TM = TransitionManifest.model_validate({"transition_id": "t", "version": "1", "description": "d",
                                        "irreversibility": IOTA, "reversible_max": 0.3, "path_epsilon": 0.05,
                                        "uncertainty_floor": 0.01})
W = TransitionWeights(lambda_irreversibility=1.0, lambda_uncertainty=0.5, lambda_voi=0.25)
ROB = RobustnessWeights(cvar_alpha=0.9, lambda_tail=1.0, lambda_var=0.0)
EPS = {**{k: 0.01 for k in OBJECTIVES if k not in ("J_R", "J_P")}, PATH_OBJECTIVE: 0.05}
OMEGA = ("m", "o")


def _answer(lo: float, hi: float, status: str = "EXPLORATORY_ONLY") -> CausalAnswer:
    return CausalAnswer("e", status, UncertainValue.bounds(lo, hi), IdentificationGrade.I7, "fictif")


def _j(**kw: Any) -> dict[str, Any]:
    w: dict[str, Any] = {k: 0.5 for k in OBJECTIVES}
    w.update({"J_R": None, "J_P": None, "J_T": 0.0, "J_pkg": 0.0, "violations": []})
    w.update(kw)
    return w


def _metrics(violations: int = 0, cost: float = 1.0, f: float = 0.5) -> dict[str, Any]:
    return {"violations": violations, "max_p_exceed": 0.5, "f_network": f, "j_conn": 0.5, "rri": [0.0, 0.5],
            "cost": cost, "complexity": 1}


def _composer(options: dict[str, dict[str, Any] | None], baseline_violations: int = 0) -> dict[str, Any]:
    return {"baseline": _metrics(baseline_violations, cost=1.0),
            "options": [{"option": k, "lo": v, "hi": v} for k, v in options.items()]}


def test_manifest_requires_every_action_and_reversible_no_change() -> None:
    with pytest.raises(ValidationError):
        TransitionManifest.model_validate({**TM.model_dump(mode="json"),
                                           "irreversibility": {**IOTA, "no_change": 0.2}})
    with pytest.raises(ValidationError):
        TransitionManifest.model_validate({**TM.model_dump(mode="json"),
                                           "irreversibility": {k: v for k, v in IOTA.items() if k != "sovereignty"}})
    assert [a.level for a in ActionType] == list(range(8))  # hiérarchie du §79, dans l'ordre


def test_uncertainty_and_voi() -> None:
    assert step_uncertainty(None, 0.01) == 1.0
    assert step_uncertainty(CausalAnswer("e", CAUSAL_EFFECT_UNKNOWN, None, None, "absent"), 0.01) == 1.0
    assert step_uncertainty(_answer(0.5, 0.9), 0.01) == pytest.approx(0.4 / 0.9)
    # On n'apprend qu'en essayant ce qu'on peut défaire, sur un effet qui n'est pas établi.
    assert voi_indicator(0.1, _answer(0.5, 0.9), 0.3) == 1.0
    assert voi_indicator(0.9, _answer(0.5, 0.9), 0.3) == 0.0
    assert voi_indicator(0.1, _answer(0.5, 0.9, "CAUSAL_FACT"), 0.3) == 0.0
    assert voi_indicator(0.1, None, 0.3) == 0.0


def test_institutional_paths_reevaluate_each_step_and_never_cross_a_violation() -> None:
    sq = Variant("sq", "STATUS_QUO", {}, {OMEGA: _j()}, relation=SqRelation.EQUAL)
    cm = CW.manifest()
    eff = {k: _answer(0.5, 0.9) for k in cm.effect_keys}
    opts = {"rights_enforcement": _metrics(cost=3.0), "representation": _metrics(cost=2.0),
            "cumul→representation": _metrics(violations=1, cost=4.0), "language_rights": None}
    paths, skipped = institutional_paths({OMEGA: _composer(opts)}, sq, cm, eff, TM)
    by_id = {p.path_id: p for p in paths}
    assert "language_rights" in skipped  # effet inconnu : jamais évalué, jamais « résolu »
    cumul = by_id["path:cumul→representation"]
    assert [s.action for s in cumul.steps] == [ActionType.RIGHTS_ENFORCEMENT, ActionType.INSTITUTIONAL_REFORM]
    assert cumul.omega[OMEGA]["violations"] == ["droits (étape 2, cumul→representation)"]
    assert by_id["path:rights_enforcement"].omega[OMEGA]["J_pkg"] == pytest.approx(2.0)  # coût au-delà du statu quo
    assert all(s.action.level >= r.action.level for p in paths for r, s in zip(p.steps, p.steps[1:], strict=False))


def test_map_r_includes_transition_cost() -> None:
    """Map-R : une frontière qui fait mieux partout sauf la transition ne domine pas le statu quo."""
    sq = Variant("sq", "STATUS_QUO", {}, {OMEGA: _j()}, relation=SqRelation.EQUAL)
    cand = Variant("c", "GEOGRAPHIC", {}, {OMEGA: _j(J_F=0.0, J_conn=0.0, J_T=0.3)}, relation=SqRelation.REFINEMENT)
    paths = [status_quo_path(sq), territorial_path(cand, "c", True, TM)]
    a = build([p.as_variant(W) for p in paths], EPS, ROB, {}, (*OBJECTIVES, PATH_OBJECTIVE), ())
    assert {s.key for s in a.solutions if s.rank == 1} == {"path:status_quo", "path:c"}  # compromis
    assert conclusion(a.conclusion, a.improving, {p.path_id: p.family for p in paths}) == "STATUS_QUO_NOT_DOMINATED"
    assert paths[1].steps[0].action is ActionType.SOVEREIGNTY and paths[1].steps[0].uncertainty == 1.0


def test_institutional_improvement_can_be_concluded() -> None:
    """À géométrie inchangée, les objectifs inconnus sont égaux : une réforme peut dominer le statu quo."""
    sq = Variant("sq", "STATUS_QUO", {}, {OMEGA: _j()}, relation=SqRelation.EQUAL)
    cm = CW.manifest()
    eff = {k: _answer(0.9, 0.95, "CAUSAL_BOUNDED") for k in cm.effect_keys}
    paths, _ = institutional_paths({OMEGA: _composer({"rights_enforcement": _metrics(cost=1.0, f=0.1)})}, sq,
                                   cm, eff, TM)
    paths = [status_quo_path(sq), next(p for p in paths if p.path_id == "path:rights_enforcement")]
    zero = TransitionWeights(lambda_irreversibility=0.0, lambda_uncertainty=0.0, lambda_voi=0.0)
    a = build([p.as_variant(zero) for p in paths], EPS, ROB, {}, (*OBJECTIVES, PATH_OBJECTIVE), ())
    fam = {p.path_id: p.family for p in paths}
    assert conclusion(a.conclusion, a.improving, fam) == "INSTITUTIONAL_PATH_IMPROVES_ON_STATUS_QUO"


def test_urgency_forbids_delay_and_voi() -> None:
    """02 §27 : en urgence, ne rien changer est infaisable ; seule une première étape corrective reste."""
    sq = Variant("sq", "STATUS_QUO", {}, {OMEGA: _j(violations=["droits:g|executive_power"])},
                 relation=SqRelation.EQUAL)
    cm = CW.manifest()
    eff = {k: _answer(0.5, 0.9) for k in cm.effect_keys}
    opts = {"rights_enforcement": _metrics(cost=3.0), "representation": _metrics(violations=1, cost=2.0)}
    inst, _ = institutional_paths({OMEGA: _composer(opts, baseline_violations=1)}, sq, cm, eff, TM)
    paths = [status_quo_path(sq), *inst]
    affected = apply_urgency(paths)
    assert "path:status_quo" in affected and "path:representation" in affected
    assert "path:rights_enforcement" not in affected
    assert all(s.voi == 0.0 for p in paths for s in p.steps)  # la sécurité prime la valeur d'information


def test_statement_is_conditional() -> None:
    s = statement("R1", ["o1", "o2"], "sha256:" + "a" * 64, None, "NOT_IDENTIFIABLE", True)
    assert "Sous le régime R1" in s and "consentement politique externe au modèle" in s and "inconnue" in s
    for word in ("devrait", "doit devenir", "prouve", "recommand"):
        assert word not in s
