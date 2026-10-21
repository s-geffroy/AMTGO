"""Red-team M11 : Goodhart (05 §14), objectifs inconnus, confidentialité et mésusage (05 §15-16).

Chaque faille trouvée devient un test de régression ici.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from amtgo.config.loader import load_model
from amtgo.core.channels import FragChannel
from amtgo.fragmentation.engine import fragmentation
from amtgo.infrastructure.hyperedges import Hyperedge, HyperedgeType
from amtgo.institutions.composer import Configuration, _cost
from amtgo.institutions.regimes import load_regime
from amtgo.manifests.normative import NormativeManifest
from amtgo.optimization.manifest import GoodhartThresholds, SensitivitySpec
from amtgo.optimization.objectives import OBJECTIVES, SqRelation, institutional_cost
from amtgo.privacy.redteam import attack_suite
from amtgo.validation import composer_worlds as CW
from amtgo.validation import goodhart
from amtgo.validation import worlds as W

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "amtgo"
TH = GoodhartThresholds(micro_state_population_share=0.05, micro_state_area_share=0.05, min_compactness=0.1,
                        max_border_protrusion_share=0.2)


def _squares(lat: W.Lattice) -> list[object]:
    from shapely.geometry import box

    h = W.SPACING_KM * 500.0
    return [box(x * 1000 - h, y * 1000 - h, x * 1000 + h, y * 1000 + h) for x, y in lat.xy]


def test_sawtooth_border_is_flagged() -> None:
    """Faille M11 (pilote) : la frontière en dents de scie gagnait sur J_V sans être signalée."""
    lat = W.Lattice(20, 12)
    adj = CW._adjacency(20, 12)
    geoms, pop = _squares(lat), np.full(lat.n, 100.0)
    straight = lat.bands([10]).levels[0].assignment
    saw = goodhart.attacks(straight, adj, pop)["GOODHART_pathological_border"]
    s_straight = goodhart.state_shapes(geoms, straight, pop, adj)  # type: ignore[arg-type]
    s_saw = goodhart.state_shapes(geoms, saw, pop, adj)  # type: ignore[arg-type]
    assert "pathological_border" not in goodhart.flags(s_straight, TH)
    assert "pathological_border" in goodhart.flags(s_saw, TH)
    # La compacité globale seule ne suffisait pas à la distinguer.
    assert s_saw["min_compactness"] > TH.min_compactness


def test_empty_overlay_buys_nothing() -> None:
    """Overlay nominal sans effet : ne réduit pas F, et coûte de la complexité (05 §14)."""
    st, part = CW.world(0.15)
    members = tuple(part.cell_ids[:10])
    empty = Hyperedge(hyperedge_id="nominal", type=HyperedgeType.TRADE, members=members,
                      mitigation={FragChannel.NETWORK: 0.0})
    f0 = {(f.group, f.channel): f.value.mean for f in fragmentation(st, part) if f.value is not None}
    f1 = {(f.group, f.channel): f.value.mean for f in fragmentation(st, part, [empty]) if f.value is not None}
    assert f0 == pytest.approx(f1)
    base = Configuration(CW._institutions(part), [])
    cost, complexity = _cost(Configuration(base.institutions, [empty]), base, CW.manifest(), len(part.cell_ids))
    assert cost > 0 and complexity >= 1


def test_continental_cost_transfer_is_counted() -> None:
    """Mutualiser la sécurité au niveau continental ne fait pas disparaître son coût (05 §14)."""
    f_admin, f_sec = 1.0, 3.0
    for rid in ("R0_CURRENT_LIKE", "R1_COMMON_MARKET", "R2_CONFEDERAL", "R3_FEDERAL_CONTINENTAL"):
        r = load_regime(ROOT / "configs", rid)
        assert institutional_cost(1, r, f_admin, f_sec, 0.0, 0.0) == pytest.approx(f_admin + f_sec)
        for n in (2, 5):
            assert institutional_cost(n, r, f_admin, f_sec, 0.0, 0.0) >= n * f_admin + f_sec - 1e-9


def test_preference_cost_is_never_inferred_from_group_shares() -> None:
    """J_P reste UNKNOWN : aucun code ne le calcule (ce serait optimiser l'homogénéité des groupes)."""
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values, strict=True):
                    if isinstance(k, ast.Constant) and k.value == "J_P":
                        assert isinstance(v, ast.Constant) and v.value is None, path


def test_unknown_objectives_never_conclude_dominance() -> None:
    from amtgo.manifests.normative import RobustnessWeights
    from amtgo.optimization.archive import Variant, build

    def omega(**kw: float) -> dict[tuple[str, str], dict[str, object]]:
        w: dict[str, object] = {k: 0.5 for k in OBJECTIVES}
        w.update({"J_R": None, "J_P": None, "violations": []}, **kw)
        return {("m", "o"): w}

    eps = {k: 0.01 for k in OBJECTIVES if k not in ("J_R", "J_P")}
    rob = RobustnessWeights(cvar_alpha=0.9, lambda_tail=1.0, lambda_var=0.0)
    for rel in SqRelation:
        if rel is SqRelation.EQUAL:
            continue
        vs = [Variant("sq", "STATUS_QUO", {}, omega(J_T=0.0), relation=SqRelation.EQUAL),
              Variant("u", "GEOGRAPHIC", {}, omega(J_T=0.5, J_D=0.0, J_F=0.0, J_conn=0.0), relation=rel)]
        a = build(vs, eps, rob, {})
        assert a.conclusion != "TERRITORIAL_OPTIONS_DOMINATE_STATUS_QUO_EXCEPT_TRANSITION", rel


def test_sensitivity_cannot_relax_hard_rights() -> None:
    with pytest.raises(ValidationError):
        SensitivitySpec.model_validate({"hard_rights": [{"right_id": "civic_equality", "relaxable": True}]})


def test_privacy_attacks_blocked_under_default_manifest() -> None:
    nm = load_model(NormativeManifest, ROOT / "configs" / "normative" / "default.yaml")
    res = attack_suite(nm.privacy)
    assert {a["attack"] for a in res} >= {"small_group_reconstruction", "public_layer_intersection",
                                          "religion_inference", "pastoral_route_inference", "minority_locator"}
    assert all(a["blocked"] for a in res)


def test_public_map_is_useless_for_targeting() -> None:
    """05 §16 : la carte publique ne porte ni groupe, ni population, ni mobilité, ni candidat non validé."""
    src = (SRC / "export" / "pages_map.py").read_text()
    for word in ("group", "share", "population", "mobility", "route"):
        assert f'"{word}' not in src, word
    assert '"candidates": [],' in src  # couche vide tant qu'aucun run ne passe les gates
