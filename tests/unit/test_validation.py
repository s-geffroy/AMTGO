"""M11 : objectifs inconnus et axiome de fusion, recomposition, stabilité, Goodhart, confidentialité."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from amtgo.causal.library import CausalAnswer
from amtgo.causal.model import CAUSAL_EFFECT_UNKNOWN
from amtgo.core.channels import IntegChannel
from amtgo.core.enums import ComputabilityClass, PrivacyClass, RecommendationStatus
from amtgo.manifests.normative import RightsThresholds, RobustnessWeights
from amtgo.optimization.archive import Variant, build
from amtgo.optimization.manifest import GoodhartThresholds, SensitivitySpec
from amtgo.optimization.objectives import (
    OBJECTIVES,
    SqRelation,
    UnknownBound,
    evaluate_geometry,
    sq_relation,
    unknown_vs_status_quo,
)
from amtgo.optimization.recompose import recompose
from amtgo.privacy.guard import ExportLayer, PrivacyAction, evaluate_release
from amtgo.privacy.redteam import attack_suite, benign_controls, gate_s
from amtgo.runs.validation_stages import multiscale
from amtgo.validation import composer_worlds as CW
from amtgo.validation import falsification, goodhart
from amtgo.validation import worlds as W
from amtgo.validation.stability import agreement, publication_category, release_allowed, s_publish

RIGHTS = RightsThresholds(severe_domination_threshold=0.5, severe_domination_probability_max=0.05,
                          urgent_domination_threshold=0.7, urgent_probability=0.5)
WEIGHTS = {c: 1.0 for c in IntegChannel}
ROB = RobustnessWeights(cvar_alpha=0.9, lambda_tail=1.0, lambda_var=0.0)
NORM = {"severe_domination_threshold": 0.5}


class _Rules:
    min_group_count = 50
    sensitive_proxies = ("religion", "language_share", "route")


def test_sq_relation_and_merge_axiom() -> None:
    sq = np.array([0, 0, 1, 1])
    assert sq_relation(np.array([1, 1, 0, 0]), sq) is SqRelation.EQUAL  # renommer n'est pas changer
    assert sq_relation(np.zeros(4, dtype=int), sq) is SqRelation.COARSENING
    assert sq_relation(np.array([0, 1, 2, 2]), sq) is SqRelation.REFINEMENT
    assert sq_relation(np.array([0, 1, 1, 0]), sq) is SqRelation.CROSSING
    # Fusionner n'abaisse jamais l'hétérogénéité interne ; scinder ne l'élève jamais.
    assert unknown_vs_status_quo("J_P", SqRelation.COARSENING) is UnknownBound.NOT_BETTER
    assert unknown_vs_status_quo("J_P", SqRelation.REFINEMENT) is UnknownBound.NOT_WORSE
    assert unknown_vs_status_quo("J_P", SqRelation.CROSSING) is UnknownBound.UNDETERMINED
    assert unknown_vs_status_quo("J_R", SqRelation.REFINEMENT) is UnknownBound.UNDETERMINED


def _omega(**objs: float | None) -> dict[tuple[str, str], dict[str, Any]]:
    base: dict[str, Any] = {k: 0.5 for k in OBJECTIVES}
    base.update({"J_R": None, "J_P": None, "violations": [], "J_D_by_threshold": {}, "_border_km": 0.0})
    base.update(objs)
    return {("m1", "o"): dict(base), ("m2", "o"): dict(base)}


EPS = {k: 0.01 for k in OBJECTIVES if k not in ("J_R", "J_P")}


def _variants(relation: SqRelation) -> list[Variant]:
    return [Variant("sq", "STATUS_QUO", {}, _omega(J_T=0.0), relation=SqRelation.EQUAL),
            Variant("cand", "GEOGRAPHIC", {"k": 1}, _omega(J_T=0.4, J_F=0.0, J_conn=0.0), relation=relation)]


def test_unknown_objective_blocks_dominance_conclusion() -> None:
    """La fusion domine sur les connus ; J_P (fusion → NOT_BETTER) et J_R empêchent de conclure."""
    a = build(_variants(SqRelation.COARSENING), EPS, ROB, NORM)
    assert a.conclusion == "DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES" and not a.improving
    assert a.unresolved["cand"] == {"J_R": "UNDETERMINED", "J_P": "NOT_BETTER"}
    # Sans J_R (objectifs restreints), un raffinement est tranché par l'axiome ; une fusion jamais.
    objs = tuple(k for k in OBJECTIVES if k != "J_R")
    assert build(_variants(SqRelation.REFINEMENT), EPS, ROB, NORM, objs).improving == ["cand"]
    assert build(_variants(SqRelation.COARSENING), EPS, ROB, NORM, objs).conclusion == \
        "DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES"


def test_no_dominance_means_no_territorial_change() -> None:
    vs = [Variant("sq", "STATUS_QUO", {}, _omega(J_T=0.0), relation=SqRelation.EQUAL),
          Variant("cand", "GEOGRAPHIC", {}, _omega(J_T=0.4, J_F=0.9), relation=SqRelation.CROSSING)]
    assert build(vs, EPS, ROB, NORM).conclusion == "NO_TERRITORIAL_CHANGE"


def test_multiscale_flags_single_mesh_dependence() -> None:
    better_on_m1 = _omega(J_T=0.0, J_F=0.0)
    better_on_m1[("m2", "o")]["J_F"] = 0.9
    vs = [Variant("sq", "STATUS_QUO", {}, _omega(J_T=0.0), relation=SqRelation.EQUAL),
          Variant("cand", "GEOGRAPHIC", {}, better_on_m1, relation=SqRelation.CROSSING)]
    ms = multiscale(vs, ["m1", "m2"], EPS, ROB, NORM)
    assert ms["single_mesh_dependent"] == ["cand"] and ms["front_meshes"]["cand"] == ["m1"]


def test_recompose_lifts_violation_or_leaves_it() -> None:
    st, part = CW.world(0.15)
    inst = CW._institutions(part)
    adj = CW._adjacency(10, 6)
    sal = CausalAnswer("none", CAUSAL_EFFECT_UNKNOWN, None, None, "absent")
    before = evaluate_geometry(st, part, inst, RIGHTS, WEIGHTS, sal, 10.0, 0.0)
    assert before["violations"]
    rc = recompose(st, part, inst, RIGHTS, WEIGHTS, CW.manifest(), CW.effects(), adj)
    assert rc.conclusion == "NO_TERRITORIAL_CHANGE_SUFFICIENT" and rc.configuration is not None and rc.cost > 0
    after = evaluate_geometry(st, part, rc.configuration.institutions, RIGHTS, WEIGHTS, sal, 10.0, 0.0,
                              rc.configuration.overlays)
    assert not after["violations"]
    weak = recompose(st, part, inst, RIGHTS, WEIGHTS, CW.manifest(), CW.effects(scale=0.1), adj)
    assert weak.configuration is None and weak.cost == 0.0  # jamais une relaxation


def test_alternative_thresholds_are_monotone() -> None:
    st, part = CW.world(0.15)
    sal = CausalAnswer("none", CAUSAL_EFFECT_UNKNOWN, None, None, "absent")
    r = evaluate_geometry(st, part, CW._institutions(part), RIGHTS, WEIGHTS, sal, 10.0, 0.0,
                          alt_thresholds=(0.3, 0.7))
    by = r["J_D_by_threshold"]
    assert by["0.3"] >= r["J_D"] >= by["0.7"]  # un seuil plus bas ne peut que révéler plus de domination


def test_stability_and_publication_category() -> None:
    assert s_publish({"a": 0.9, "b": None}) is None and s_publish({"a": 0.9, "b": 0.7}) == 0.7
    nominal = {"x": (True, True), "y": (True, False)}
    assert agreement(nominal, [{"x": (True, True), "y": (True, True)}]) == {"x": 1.0, "y": 0.0}
    assert agreement(nominal, []) == {"x": None, "y": None}
    ok = {"M": "PASSED", "O": "PASSED", "S": "PASSED", "R": "PASSED"}
    cat = publication_category
    assert cat(ok, None, 0.8, ComputabilityClass.A, "X", False, False) is RecommendationStatus.NOT_IDENTIFIABLE
    assert cat(ok, 0.9, 0.8, ComputabilityClass.A, "DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES", False, False) \
        is RecommendationStatus.NOT_IDENTIFIABLE
    assert cat(ok, 0.9, 0.8, ComputabilityClass.C, "X", False, False) is RecommendationStatus.DATA_LIMITED
    assert cat({**ok, "S": "FAILED"}, 0.9, 0.8, ComputabilityClass.A, "X", False, False) \
        is RecommendationStatus.EXPLORATORY
    assert cat(ok, 0.7, 0.8, ComputabilityClass.B, "X", False, False) is RecommendationStatus.EXPLORATORY
    assert cat(ok, 0.9, 0.8, ComputabilityClass.B, "X", True, False) is RecommendationStatus.CONDITIONAL
    assert cat(ok, 0.9, 0.8, ComputabilityClass.B, "X", False, True) is RecommendationStatus.CONDITIONAL
    assert cat(ok, 0.9, 0.8, ComputabilityClass.A, "X", False, False) is RecommendationStatus.ROBUST
    assert release_allowed(RecommendationStatus.ROBUST, ok)
    assert not release_allowed(RecommendationStatus.ROBUST, {**ok, "R": "NOT_EVALUABLE"})
    assert not release_allowed(RecommendationStatus.EXPLORATORY, ok)


def test_goodhart_detectors_on_lattice() -> None:
    lat = W.Lattice(20, 12)
    sq = lat.bands([10]).levels[0].assignment
    adj = CW._adjacency(20, 12)
    pop = np.full(lat.n, 100.0)
    geoms = [_square(x, y) for x, y in lat.xy]
    th = GoodhartThresholds(micro_state_population_share=0.05, micro_state_area_share=0.05, min_compactness=0.1,
                            max_border_protrusion_share=0.2)
    assert goodhart.flags(goodhart.state_shapes(geoms, sq, pop, adj), th) == []
    attacks = goodhart.attacks(sq, adj, pop)
    assert set(attacks) == {"GOODHART_micro_territory", "GOODHART_artificial_metropolis",
                            "GOODHART_pathological_border"}
    for name, a in attacks.items():
        assert goodhart.flags(goodhart.state_shapes(geoms, a, pop, adj), th), name


def _square(x: float, y: float) -> Any:
    from shapely.geometry import box

    h = W.SPACING_KM * 500.0
    return box(x * 1000 - h, y * 1000 - h, x * 1000 + h, y * 1000 + h)


def test_manifest_sections_validate() -> None:
    with pytest.raises(ValidationError):
        SensitivitySpec(severe_domination_threshold=(1.5,))
    with pytest.raises(ValidationError):
        SensitivitySpec(epsilon_scale=(0.0,))
    assert SensitivitySpec(severe_domination_threshold=(0.4,), epsilon_scale=(2.0,)).size == 2
    with pytest.raises(ValidationError):
        GoodhartThresholds(micro_state_population_share=0.0, micro_state_area_share=0.05, min_compactness=0.1,
                           max_border_protrusion_share=0.2)


def test_release_rules() -> None:
    P = PrivacyClass.PUBLIC
    small = ExportLayer("pop", P, True, False, False, 10, ("population",), "g", 3.0)
    d = evaluate_release([small], _Rules(), PrivacyClass.CONTROLLED)
    assert d["pop"].action is PrivacyAction.SUPPRESS
    a = ExportLayer("a", P, True, False, False, 10, ("population",), "grid", 500.0)
    b = ExportLayer("b", P, True, False, False, 10, ("population",), "hex", 500.0)
    same = ExportLayer("c", P, True, False, False, 10, ("population",), "grid", 500.0)
    d = evaluate_release([a, b, same], _Rules(), PrivacyClass.CONTROLLED)
    assert d["a"].released and not d["b"].released and d["c"].released  # même support : rien à différencier
    lang = ExportLayer("lang", P, False, False, False, 10, ("language_share",), "grid")
    assert evaluate_release([lang], _Rules())["lang"].action is PrivacyAction.RESTRICT
    derived = ExportLayer("cand", P, False, False, False, 2, ("boundary",), "grid", derived_from_group_attributes=True)
    assert evaluate_release([derived], _Rules())["cand"].action is PrivacyAction.RESTRICT


def test_privacy_red_team_and_gate_s(monkeypatch: pytest.MonkeyPatch) -> None:
    assert all(a["blocked"] for a in attack_suite(_Rules()))
    assert all(c["released"] for c in benign_controls(_Rules()))  # le garde n'est pas « tout bloquer »
    mesh = ExportLayer("mesh", PrivacyClass.PUBLIC, False, False, False, 10, ("geometry",), "grid")
    assert gate_s([mesh], _Rules())["gate_s"] == "PASSED"
    # Un garde dégénéré qui laisse tout sortir échoue au gate.
    from amtgo.privacy import redteam
    from amtgo.privacy.guard import PrivacyDecision

    def leaky(layers: list[ExportLayer], *_: Any, **__: Any) -> dict[str, PrivacyDecision]:
        return {x.name: PrivacyDecision(PrivacyAction.ALLOW, "fuite") for x in layers}

    monkeypatch.setattr(redteam, "evaluate_release", leaky)
    pop = ExportLayer("pop", PrivacyClass.PUBLIC, True, True, False, 10, ("group_share",), "grid")
    assert redteam.gate_s([pop], _Rules())["gate_s"] == "FAILED"


def test_falsification_controls() -> None:
    res = {c["control"]: c["status"] for c in falsification.run_controls()}
    assert res["ethnic_states_everywhere"] == res["ethnic_metropolis"] == res["pastoral_corridor_state"] == "PASSED"
    # Les contrôles qui exigent des données réelles ne sont jamais réputés passés.
    assert res["rwanda_hutu_tutsi_partition"] == "NOT_APPLICABLE"
