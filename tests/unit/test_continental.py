"""Coordination continentale (M14) : agrégation, couches, relations, exactitude de la décomposition."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from amtgo.manifests.normative import RobustnessWeights
from amtgo.optimization import continental as cont
from amtgo.optimization.archive import build
from amtgo.optimization.objectives import SqRelation

ROB = RobustnessWeights(cvar_alpha=0.9, lambda_tail=1.0, lambda_var=0.0)
EPS = {"J_D": 0.01, "J_F": 0.0005, "J_conn": 0.0001, "J_V": 0.02, "J_G": 0.005, "J_T": 0.01, "J_inst": 1.0,
       "J_pkg": 0.05, "J_reif": 0.001, "J_path": 0.05}
NORM = {"severe_domination_threshold": 0.5, "severe_domination_probability_max": 0.05}
W = ("p", "o")


def vals(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"J_D": 0.0, "J_F": 0.0, "J_conn": 0.0, "J_V": 0.1, "J_G": 0.1, "J_R": None,
                            "J_P": None, "J_T": 0.0, "J_inst": 10.0, "J_pkg": 0.0, "J_reif": 0.0, "J_path": 0.0,
                            "violations": []}
    return {**base, **kw}


def opt(region: str, key: str, rel: SqRelation = SqRelation.EQUAL, family: str = "PATH_TERRITORIAL",
        **kw: Any) -> cont.RegionOption:
    if key == "sq":
        family = "STATUS_QUO"
    return cont.RegionOption(region, key, family, "border_change", {W: vals(**kw)}, rel, {})


def world(mu: tuple[float, float] = (0.0, 0.5), cost: tuple[float, float] = (1.0, 2.0), border_km: float = 10.0,
          cross: float = 50.0, sec: bool = False) -> cont.World:
    layers = {"market": cont.LayerEffect("market", "cross_links", mu, cost, 0.5)}
    if sec:
        layers["security"] = cont.LayerEffect("security", "border_cost", mu, cost, 0.5)
    return cont.World({"a": {"p": cont.RegionTotals(100.0, 100.0)}, "b": {"p": cont.RegionTotals(300.0, 200.0)}},
                      [cont.Interface("a", "b", border_km, {"p": {("market",): cross}})], layers, 1.0)


def test_aggregation_rules() -> None:
    c = cont.Composite({"a": opt("a", "x", J_D=0.2, J_T=0.4, J_G=0.1, J_inst=5.0, J_reif=None),
                        "b": opt("b", "y", J_D=0.1, J_T=0.0, J_G=0.4, J_inst=7.0)}, {"a~b": ()})
    row = cont.evaluate(c, world())[W]
    assert row["J_D"] == 0.2  # pire cas : une violation ne se compense pas ailleurs
    assert row["J_T"] == pytest.approx(0.4 * 100 / 400)  # part de la population continentale
    # J_G : liens inter-régionaux toujours coupés, au dénominateur et au numérateur
    assert row["J_G"] == pytest.approx((0.1 * 100 + 0.4 * 200 + 50) / (100 + 200 + 50))
    assert row["J_inst"] == pytest.approx(5.0 + 7.0 + 10.0 * 1.0)  # + frontière d'interface, invisible en région
    assert row["J_reif"] is None and row["J_P"] is None and row["J_R"] is None  # UNKNOWN n'est jamais 0


def test_layers_robust_and_optimistic_bounds() -> None:
    sq = {"a": opt("a", "sq"), "b": opt("b", "sq")}
    w = world(mu=(0.2, 0.6), cost=(1.0, 3.0), sec=True)
    none = cont.evaluate(cont.Composite(sq, {"a~b": ()}), w)[W]
    rob = cont.evaluate(cont.Composite(sq, {"a~b": ("market", "security")}), w)[W]
    opt_ = cont.evaluate(cont.Composite(sq, {"a~b": ("market", "security")}), w, cont.OPTIMISTIC)[W]
    den = 100 + 200 + 50
    assert rob["J_G"] == pytest.approx((10 + 20 + 50 * 0.8) / den)  # μ basse
    assert opt_["J_G"] == pytest.approx((10 + 20 + 50 * 0.4) / den)  # μ haute
    assert rob["J_inst"] == pytest.approx(20.0 + 10.0 * 0.8 + 2 * 3.0)  # coût haut, sécurité sur la frontière
    assert rob["J_path"] == pytest.approx(1.0) and none["J_path"] == 0.0


def test_zero_effect_layer_never_dominates_absence() -> None:
    sq = {"a": opt("a", "sq"), "b": opt("b", "sq")}
    w = world(mu=(0.0, 0.5))
    comp = cont.compose({"a": [sq["a"]], "b": [sq["b"]]}, w, EPS, ROB, NORM, {"a": {"sq"}, "b": {"sq"}})
    assert comp.layer_improving["a~b"] == []  # à la borne robuste, une couche n'ajoute que du coût
    optimistic = cont.compose({"a": [sq["a"]], "b": [sq["b"]]}, w, EPS, ROB, NORM, {"a": {"sq"}, "b": {"sq"}},
                              bound=cont.OPTIMISTIC)
    assert ("market",) in optimistic.layer_fronts["a~b"]  # priorité de recherche, pas résultat


def test_relations_compose_and_merge_axiom_blocks() -> None:
    assert cont.combine_relations([SqRelation.EQUAL, SqRelation.EQUAL]) is SqRelation.EQUAL
    assert cont.combine_relations([SqRelation.COARSENING, SqRelation.EQUAL]) is SqRelation.COARSENING
    assert cont.combine_relations([SqRelation.COARSENING, SqRelation.REFINEMENT]) is SqRelation.CROSSING
    # Une fusion dans une région, meilleure sur tous les objectifs connus : la dominance du statu quo
    # n'est pas établie (J_P NOT_BETTER), comme dans une région (M13).
    options = {"a": [opt("a", "sq"), opt("a", "union", SqRelation.COARSENING, J_G=0.0, J_inst=1.0)],
               "b": [opt("b", "sq")]}
    comp = cont.compose(options, world(), EPS, ROB, NORM, {"a": {"sq", "union"}, "b": {"sq"}})
    sq = next(s for s in comp.archive.solutions if s.family == "STATUS_QUO")
    assert sq.rank == 1
    assert comp.archive.improving == [] and comp.archive.unresolved
    assert cont.conclusion(comp.archive) == "DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES"


def _random_options(rng: np.random.Generator, region: str, n: int) -> list[cont.RegionOption]:
    out = [opt(region, "sq")]
    for i in range(n):
        rel = SqRelation(rng.choice(["REFINEMENT", "COARSENING", "CROSSING"]))
        out.append(opt(region, f"o{i}", rel, J_D=float(rng.uniform(0, 0.03)), J_G=float(rng.uniform(0, 0.2)),
                       J_T=float(rng.uniform(0, 0.5)), J_inst=float(rng.uniform(5, 15)),
                       J_path=float(rng.uniform(0, 3))))
    return out


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_decomposition_matches_exhaustive_enumeration(seed: int) -> None:
    """07 §14 : le front composé coïncide avec celui de l'énumération exhaustive."""
    rng = np.random.default_rng(seed)
    options = {"a": _random_options(rng, "a", 6), "b": _random_options(rng, "b", 6)}
    w = world(mu=(0.1, 0.4), cost=(0.5, 1.0), sec=True)
    regional_front = {}
    for r, opts in options.items():  # front régional (seul, interface ignorée)
        alone = cont.World({r: w.totals[r]}, [], w.layers, 1.0)
        a = build(cont.to_variants([cont.Composite({r: o}, {}) for o in opts], alone), EPS, ROB, NORM,
                  cont.OBJECTIVES_C, sq_comparison_excludes=())
        regional_front[r] = {k.split("=", 1)[1] for k in a.front}
    comp = cont.compose(options, w, EPS, ROB, NORM, regional_front)
    front = set(comp.archive.front)
    full = cont._product(options, {"a~b": cont.layer_choices(w)})
    check = cont.exactness_check("tout", full, front, w, EPS, ROB, 5000)
    assert check["checked"] and check["exact"], check


def test_vectorized_front_matches_archive() -> None:
    rng = np.random.default_rng(7)
    options = {"a": _random_options(rng, "a", 5), "b": _random_options(rng, "b", 5)}
    w = world()
    vs = cont.to_variants(cont._product(options, {"a~b": [()]}), w)
    a = build(vs, EPS, ROB, NORM, cont.OBJECTIVES_C, sq_comparison_excludes=())
    assert cont.first_front(vs, EPS, ROB) == set(a.front)


def test_verdicts_need_dominance_and_separation_needs_all() -> None:
    eps = {"J_D": 0.01, "J_reif": 0.001}

    def row(pid: str, family: str, action: str, feasible: bool = True, **o: float) -> dict[str, Any]:
        return {"path_id": pid, "name": pid, "family": family, "top_action": action, "feasible": feasible,
                "steps": [{"payload": {}}], "objectives": {"J_D": 0.0, "J_reif": 0.0, **o}}

    rows = [row("sq", "STATUS_QUO", "no_change"), row("t", "PATH_TERRITORIAL", "border_change"),
            row("s1", "PATH_TERRITORIAL", "sovereignty", J_D=0.05),
            row("s2", "PATH_TERRITORIAL", "sovereignty", feasible=False)]
    v = cont.regional_verdicts(rows, [], eps)
    assert "territorialisation_utile" not in v["established"]  # un compromis au front n'établit rien
    assert v["established"]["separation_supplementaire_dangereuse"] == ["s1", "s2"]
    # Une réification plus forte (borne haute d'un effet déclaré) est un signal, pas une preuve de danger.
    rows[2] = row("s1", "PATH_TERRITORIAL", "sovereignty", J_reif=0.1)
    v = cont.regional_verdicts(rows, ["t"], eps)
    assert "separation_supplementaire_dangereuse" not in v["established"]
    assert v["reification_signals"] == {"s1": ["J_reif"]}
    assert v["established"]["territorialisation_utile"] == ["t"]


def test_worst_category() -> None:
    assert cont.worst_category(["ROBUST", "CONDITIONAL"]) == "CONDITIONAL"
    assert cont.worst_category(["ROBUST", "NOT_IDENTIFIABLE"]) == "NOT_IDENTIFIABLE"


def test_exactness_check_detects_pruning_loss() -> None:
    """Le max masque une dominance régionale : l'élagage perd une option, et le contrôle le dit."""
    options = {"a": [opt("a", "sq", J_D=0.0, J_G=0.1),
                     opt("a", "better", SqRelation.CROSSING, J_D=0.0, J_G=0.05),
                     opt("a", "pruned", SqRelation.CROSSING, J_D=0.02, J_G=0.052)],
               "b": [opt("b", "sq", J_D=0.03)]}
    w = world()
    regional_front = {"a": {"sq", "better"}, "b": {"sq"}}  # « pruned » est dominé dans sa région
    comp = cont.compose(options, w, EPS, ROB, NORM, regional_front)
    full = cont._product(options, {"a~b": cont.layer_choices(w)})
    check = cont.exactness_check("tout", full, set(comp.archive.front), w, EPS, ROB, 5000)
    assert check["checked"] and not check["exact"] and check["missed"] >= 1
    repaired = cont.verify_and_repair(comp, options, w, EPS, ROB, NORM, 5000)
    assert repaired.repaired and any("pruned" in k for k in repaired.archive.front)
    full_front = cont.exactness_check("tout", full, set(repaired.archive.front), w, EPS, ROB, 5000)
    assert full_front["exact"], full_front
