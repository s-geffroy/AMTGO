"""Rapport des mondes synthétiques A–F (D/F/I) et V (viabilité) : publiable, catégories fictives."""

from __future__ import annotations

from typing import Any

from amtgo.core.channels import FragChannel, IntegChannel
from amtgo.domination.engine import domination
from amtgo.fragmentation.engine import fragmentation
from amtgo.institutions.regimes import ConstitutionalRegime
from amtgo.integration.engine import integration
from amtgo.manifests.normative import RightsThresholds, ViabilityThresholds
from amtgo.validation import viability_worlds as V
from amtgo.validation import worlds as W


def evaluate_all(rights: RightsThresholds, weights: dict[IntegChannel, float]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    cases = [W.world_a(), W.world_b(), W.world_c(), W.world_d(), W.world_e(), W.world_f(),
             W.world_f(shared_identity=True, strong_ties=True)]
    cases[-1].name = "F'"
    for w in cases:
        res: dict[str, Any] = {}
        for name, p in w.probes.items():
            ov = w.overlays.get(name, [])
            frag = {f"{f.group}|{f.channel.value}": (None if f.value is None else f.value.mean)
                    for f in fragmentation(w.state, p, ov)}
            j = integration(w.state, p, weights, ov).j_conn
            dom = [d for d in domination(w.state, p, w.institutions[name], rights)] if name in w.institutions else []
            res[name] = {"j_conn": None if j is None else j.mean, "fragmentation": frag,
                         "domination": [{"group": d.group, "domain": d.domain.value, "D_pot": d.potential.mean,
                                         "p_exceed": d.p_exceed, "violation": d.violation} for d in dom]}
        out[w.name] = res
    return out


def checks(r: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """Propriétés qualitatives attendues (ADR-0010) : (énoncé, vérifiée ?, valeurs)."""
    f = FragChannel
    c, d, e = r["C"], r["D"], r["E"]
    ex = {x["group"]: x for x in e["excluded"]["domination"] if x["domain"] == "executive_power"}
    exr = {x["group"]: x for x in e["excluded_with_rights"]["domination"] if x["domain"] == "executive_power"}

    def p_mob(k: str) -> float:
        return float(c[k]["fragmentation"][f"p|{f.MOBILITY.value}"])

    fa, fb = r["F"]["current_border"]["fragmentation"], r["F'"]["current_border"]["fragmentation"]
    return [
        ("A vs B : couper deux populations séparées rompt bien moins que couper deux populations intégrées",
         r["A"]["split"]["j_conn"] < 0.25 * r["B"]["split"]["j_conn"],
         f"J_conn A {r['A']['split']['j_conn']:.4f} ; B {r['B']['split']['j_conn']:.4f}"),
        ("C : un overlay de corridor atténue fortement la fragmentation de mobilité des pastoraux",
         p_mob("three_hard_overlay") < 0.5 * p_mob("three_hard"),
         f"F_mob(p) dur {p_mob('three_hard'):.3f} ; overlay {p_mob('three_hard_overlay'):.3f} ; "
         f"régime de mobilité {p_mob('three_soft_mobility'):.3f}"),
        ("D : couper la métropole mixte rompt plus que la laisser entière",
         d["split_metro"]["j_conn"] > 2 * d["metro_whole"]["j_conn"],
         f"J_conn coupée {d['split_metro']['j_conn']:.4f} ; entière {d['metro_whole']['j_conn']:.4f}"),
        ("E : majorité exclue → D > 0 et contrainte de droits violée ; levée par des garde-fous",
         ex["m"]["violation"] and not exr["m"]["violation"],
         f"D_pot(m) exclue {ex['m']['D_pot']:.2f} ; avec garde-fous {exr['m']['D_pot']:.2f}"),
        ("F : même ethnonyme, identités nationales distinctes, liens faibles → F ≈ 0",
         all(v is None or v < 0.02 for v in fa.values()),
         ", ".join(f"{k} {'UNKNOWN' if v is None else f'{v:.3f}'}" for k, v in fa.items())),
        ("F' : identité partagée et liens forts → F > 0 (la règle porte sur les liens, pas sur le nom)",
         (fb[f"x|{f.NETWORK.value}"] or 0) > 0.05,
         f"F réseau {fb[f'x|{f.NETWORK.value}']:.3f} ; culturel {fb[f'x|{f.CULTURAL.value}']:.3f}"),
    ]


def all_checks(rights: RightsThresholds, weights: dict[IntegChannel, float],
               regimes: dict[str, ConstitutionalRegime], viability: ViabilityThresholds,
               observed: str = "R0_CURRENT_LIKE") -> list[tuple[str, bool, str]]:
    """Propriétés des mondes A–F (D/F/I) et du monde V (viabilité contextuelle, M6)."""
    return checks(evaluate_all(rights, weights)) + V.checks(V.evaluate(regimes, observed, viability), observed)


def render(rights: RightsThresholds, weights: dict[IntegChannel, float],
           regimes: dict[str, ConstitutionalRegime], viability: ViabilityThresholds) -> str:
    lines = ["# Mondes synthétiques A–F et V\n",
             "> Mondes **fictifs** à vérité connue (prompt §56). A–F vérifient les composantes D/F/I, "
             "V la viabilité contextuelle, que l'optimiseur utilisera (M10) ; ils ne produisent aucune "
             "recommandation.\n",
             "| propriété attendue | vérifiée | valeurs |", "|---|---|---|"]
    for text, ok, vals in all_checks(rights, weights, regimes, viability):
        lines.append(f"| {text} | {'oui' if ok else '**NON**'} | {vals} |")
    return "\n".join(lines) + "\n"
