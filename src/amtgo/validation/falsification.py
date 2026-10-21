"""Contrôles de falsification (05 §11, 11 phase 8) sur les mondes synthétiques A–F.

Le modèle est suspect s'il produit des États ethniques partout, attribue une
métropole à un groupe, transforme un corridor pastoral en État continu… Chaque
contrôle compare deux partitions sondes d'un monde à vérité connue sur les
objectifs D/F/I de l'archive (ε-dominance, minimisation) et vérifie que le
modèle ne préfère pas la réponse suspecte. Les contrôles qui exigent des données
réelles (Rwanda, Afrique du Sud, Sahara, frontières EPR) sont déclarés
NOT_APPLICABLE sur un monde synthétique, jamais réputés passés.
"""

from __future__ import annotations

from typing import Any

from amtgo.core.channels import FragChannel, IntegChannel
from amtgo.fragmentation.engine import fragmentation
from amtgo.geo.partition import Partition
from amtgo.infrastructure.hyperedges import Hyperedge
from amtgo.integration.engine import integration
from amtgo.optimization.pareto import eps_dominates
from amtgo.validation.worlds import World, world_b, world_c, world_d

# Résolution des comparaisons : ε nul, toute différence compte (mondes sans bruit de modèle).
_EPS = {"J_F": 0.0, "J_conn": 0.0}
_WEIGHTS = {c: 1.0 for c in IntegChannel}


def _objectives(world: World, probe: str, overlays: list[Hyperedge] | None = None) -> dict[str, float | None]:
    part: Partition = world.probes[probe]
    frag = fragmentation(world.state, part, overlays)
    pop = world.state.population.sum(axis=1).mean(axis=0)
    net = {f.group: f.value.mean or 0.0 for f in frag if f.channel is FragChannel.NETWORK and f.value is not None}
    integ = integration(world.state, part, _WEIGHTS, overlays)
    return {"J_F": float(sum(net.get(g, 0.0) * pop[i] for i, g in enumerate(world.state.groups)) / pop.sum()),
            "J_conn": None if integ.j_conn is None else float(integ.j_conn.mean or 0.0)}


def _mobility(world: World, probe: str, group: str) -> float:
    est = fragmentation(world.state, world.probes[probe], world.overlays.get(probe))
    return next(f.value.mean or 0.0 for f in est
                if f.channel is FragChannel.MOBILITY and f.group == group and f.value is not None)


def run_controls() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    b = world_b()
    split, unified = _objectives(b, "split"), _objectives(b, "unified")
    out.append({"control": "ethnic_states_everywhere", "world": "B",
                "expected": "la partition alignée sur les groupes ne domine pas l'unité intégrée",
                "status": "PASSED" if not eps_dominates(split, unified, _EPS) else "FAILED",
                "objectives": {"split": split, "unified": unified}})
    d = world_d()
    cut, whole = _objectives(d, "split_metro"), _objectives(d, "metro_whole")
    out.append({"control": "ethnic_metropolis", "world": "D",
                "expected": "couper la métropole mixte ne domine pas la laisser entière",
                "status": "PASSED" if not eps_dominates(cut, whole, _EPS) else "FAILED",
                "objectives": {"split_metro": cut, "metro_whole": whole}})
    c = world_c()
    hard, overlay = _mobility(c, "three_hard", "p"), _mobility(c, "three_hard_overlay", "p")
    out.append({"control": "pastoral_corridor_state", "world": "C",
                "expected": "le corridor pastoral appelle un overlay, pas un État continu",
                "status": "PASSED" if overlay < hard else "FAILED",
                "objectives": {"three_hard": hard, "three_hard_overlay": overlay}})
    for control in ("rwanda_hutu_tutsi_partition", "rsa_automatic_balkanisation", "sahara_homogeneous_polygon",
                    "epr_border_reproduction"):
        out.append({"control": control, "world": None, "status": "NOT_APPLICABLE",
                    "expected": "exige des données réelles (pilote réel, 11 phase 8)"})
    return out
