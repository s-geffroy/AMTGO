"""Mondes synthétiques I : composeur institutionnel à géométrie fixe (M9, gate de la phase 4).

Deux États fictifs, deux districts chacun. Un groupe minoritaire « n »,
représenté proportionnellement, sous une règle majoritaire et des garde-fous
faibles : la domination potentielle sur le pouvoir exécutif viole la contrainte
de droits. Propriétés attendues :

- avec une application des droits d'efficacité plausible, le composeur conclut
  NO_TERRITORIAL_CHANGE_SUFFICIENT — sans redessiner ;
- avec des effets quasi nuls, il conclut INSTITUTIONAL_INSUFFICIENT_AT_FIXED_GEOMETRY,
  sans jamais proposer de frontière ;
- sans violation au statu quo, il conclut NO_CHANGE ;
- un overlay dont l'effet est inconnu ne réduit rien (Goodhart, 05 §14) ;
- dévoluer des compétences vers des districts alignés sur un groupe accroît le
  risque de réification, alors que l'application des droits ne le change pas.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from amtgo.causal.library import CausalAnswer
from amtgo.causal.model import CAUSAL_EFFECT_UNKNOWN, IdentificationGrade
from amtgo.core.channels import IntegChannel
from amtgo.core.uncertainty import UncertainValue
from amtgo.geo.partition import Partition, PartitionLevel
from amtgo.institutions.competences import (
    CompetenceVector,
    DecisionRule,
    Domain,
    Institution,
    Representation,
    RightsProfile,
)
from amtgo.institutions.composer import ComposerManifest, compose
from amtgo.manifests.normative import RightsThresholds
from amtgo.validation import worlds as W

UPPER = {Domain.EXECUTIVE_POWER: 1.0, Domain.SECURITY: 1.0, Domain.PUBLIC_EMPLOYMENT: 0.6,
         Domain.PUBLIC_SERVICES: 0.5, Domain.CULTURE_LANGUAGE: 0.7, Domain.LOCAL_GOVERNMENT: 0.2}
LOWER = {Domain.PUBLIC_EMPLOYMENT: 0.4, Domain.PUBLIC_SERVICES: 0.5, Domain.CULTURE_LANGUAGE: 0.3,
         Domain.LOCAL_GOVERNMENT: 0.8}


def manifest() -> ComposerManifest:
    return ComposerManifest.model_validate({
        "composer_id": "world_i", "version": "1", "description": "monde I", "upper_level": "state",
        "local_level": "district", "salience_effect": "salience", "horizon_years": 10, "overlay_ring": 1,
        "cost": {"units": "fictives", "coordination_per_shared_domain": 1.0, "enforcement_per_check_unit": 1.0,
                 "threshold_change_per_unit": 1.0, "overlay_per_cell_share": 1.0},
        "levers": [
            {"lever": "rights_enforcement", "effect": "rights", "target_checks": 0.8},
            {"lever": "representation", "effect": "representation", "threshold": 0.67},
            {"lever": "language_rights", "effect": "language", "domains": ["culture_language"], "target_checks": 0.9},
            {"lever": "functional_overlay", "effect": "overlay", "channels": ["network"]},
            {"lever": "fiscal_autonomy", "effect": "devolution", "domains": ["public_services", "public_employment"],
             "shift": 0.3},
            {"lever": "territorial_autonomy", "effect": "devolution",
             "domains": ["local_government", "culture_language", "public_services"], "shift": 0.6},
            {"lever": "sovereignty"},
        ]})


def effects(scale: float = 1.0, overlay_known: bool = True) -> dict[str, CausalAnswer]:
    """Efficacités I7 du monde I ; ``scale`` les réduit (monde à effets quasi nuls)."""
    def bounds(key: str, lo: float, hi: float) -> CausalAnswer:
        return CausalAnswer(key, "EXPLORATORY_ONLY", UncertainValue.bounds(lo * scale, hi * scale),
                            IdentificationGrade.I7, "monde I (fictif)")
    out = {"rights": bounds("rights", 0.5, 0.9), "representation": bounds("representation", 0.6, 1.0),
           "language": bounds("language", 0.5, 0.9), "devolution": bounds("devolution", 0.5, 0.9),
           "salience": CausalAnswer("salience", "EXPLORATORY_ONLY", UncertainValue.bounds(0.0, 0.5),
                                    IdentificationGrade.I7, "monde I (fictif)")}
    out["overlay"] = (bounds("overlay", 0.3, 0.6) if overlay_known else
                      CausalAnswer("overlay", CAUSAL_EFFECT_UNKNOWN, None, None, "aucun effet identifié"))
    return out


def _institutions(partition: Partition) -> dict[str, list[Institution]]:
    def inst(jid: str, level: str, auth: dict[Domain, float]) -> Institution:
        return Institution(jurisdiction_id=jid, level=level, competences=CompetenceVector(authority=auth),
                           decision={}, default_decision=DecisionRule(threshold=0.5),
                           rights=RightsProfile(checks={}, default=0.2),
                           representation=Representation(rule="proportional"))
    return {lv.name: [inst(j, lv.name, UPPER if lv.name == "state" else LOWER) for j in lv.jurisdictions]
            for lv in partition.levels}


def world(minority_share: float, concentrated: bool = False) -> tuple[Any, Partition]:
    lat = W.Lattice(10, 6)
    x, y = lat.xy[:, 0] / W.SPACING_KM, lat.xy[:, 1] / W.SPACING_KM
    share = np.full(lat.n, minority_share)
    if concentrated:  # minorité concentrée dans un district (nord-est) : districts alignés sur le groupe
        share = np.where((x >= 5) & (y >= 3), 0.6, 0.04)
    e = np.column_stack([200.0 * (1 - share), 200.0 * share])
    st = W._state("I", lat, ["m", "n"], e, 9)
    state = (x >= 5).astype(int)
    district = state * 2 + (y >= 3).astype(int)
    part = Partition("lattice", lat.ids, [
        PartitionLevel("state", state, ["state_w", "state_e"], W.HARD),
        PartitionLevel("district", district, ["d_wn", "d_ws", "d_en", "d_es"], W.border(P=0.3, C=0.0, E=0.05,
                                                                                       M=0.0, R=0.1, S=0.0))])
    return st, part


def _adjacency(nx: int, ny: int) -> list[list[int]]:
    out = []
    for yy in range(ny):
        for xx in range(nx):
            out.append([yy2 * nx + xx2 for xx2, yy2 in ((xx - 1, yy), (xx + 1, yy), (xx, yy - 1), (xx, yy + 1))
                        if 0 <= xx2 < nx and 0 <= yy2 < ny])
    return out


def evaluate_all(rights: RightsThresholds, weights: dict[IntegChannel, float]) -> dict[str, Any]:
    m = manifest()
    adj = _adjacency(10, 6)
    out = {}
    for name, share, conc, eff in (("violation", 0.15, False, effects()),
                                   ("weak_effects", 0.15, False, effects(scale=0.1)),
                                   ("no_violation", 0.4, False, effects()),
                                   ("unknown_overlay", 0.15, False, effects(overlay_known=False)),
                                   ("concentrated", 0.15, True, effects())):
        st, part = world(share, conc)
        out[name] = compose(st, part, _institutions(part), rights, weights, m, eff, adj)
    return out


def checks(r: dict[str, Any]) -> list[tuple[str, bool, str]]:
    def option(res: dict[str, Any], name: str) -> dict[str, Any]:
        return next(o for o in res["options"] if o["option"] == name)

    v, w, n, u, c = r["violation"], r["weak_effects"], r["no_violation"], r["unknown_overlay"], r["concentrated"]
    ov_known, ov_unknown = option(v, "functional_overlay"), option(u, "functional_overlay")
    f_base = v["baseline"]["f_network"]
    rri_aut = option(c, "territorial_autonomy")["hi"]["rri"]
    rri_rights = option(c, "rights_enforcement")["hi"]["rri"]
    return [
        ("I : violation au statu quo, levée par l'application des droits → NO TERRITORIAL CHANGE",
         v["conclusion"] == "NO_TERRITORIAL_CHANGE_SUFFICIENT" and v["chosen"] == "rights_enforcement",
         f"{v['conclusion']} via {v['chosen']} (violations {v['baseline']['violations']} → "
         f"{option(v, 'rights_enforcement')['lo']['violations']})"),
        ("I : effets quasi nuls → insuffisant à géométrie fixe, sans proposer de frontière",
         w["conclusion"] == "INSTITUTIONAL_INSUFFICIENT_AT_FIXED_GEOMETRY" and w["chosen"] is None,
         f"{w['conclusion']} ; renvoyé à la recherche territoriale : {w['deferred_to_territorial_search']}"),
        ("I : aucune violation au statu quo → NO_CHANGE (aucun biais vers l'action)",
         n["conclusion"] == "NO_CHANGE", n["conclusion"]),
        ("I : un overlay sans effet identifié ne réduit rien (Goodhart)",
         ov_unknown["status"] == "CAUSAL_EFFECT_UNKNOWN" and ov_unknown["lo"] is None
         and ov_known["lo"]["f_network"] < f_base,
         f"F réseau : base {f_base:.3f} ; overlay identifié {ov_known['lo']['f_network']:.3f} ; "
         f"overlay inconnu : {ov_unknown['status']}"),
        ("I : dévoluer vers des districts alignés accroît le risque de réification ; les droits, non",
         rri_aut is not None and rri_rights is not None and rri_aut[1] > 0 and rri_rights[1] == 0,
         f"RRI haut : autonomie territoriale {f'{rri_aut[1]:.4f}' if rri_aut else 'UNKNOWN'} ; "
         f"droits {f'{rri_rights[1]:.4f}' if rri_rights else 'UNKNOWN'}"),
    ]



