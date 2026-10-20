"""Vecteur d'objectifs J d'une géométrie candidate (02 §17, prompt §41-42).

    J = [J_D, J_F, J_conn, J_V, J_G, J_R, J_T, J_inst, J_reif]      (tous à minimiser)

- J_D : max P(D > τ) sur groupes × juridictions × domaines ; la contrainte de
  droits (aucune violation) est une **contrainte dure**, pas un objectif pondéré ;
- J_F : fragmentation réseau pondérée par la population des groupes ;
- J_conn : coût de rupture des connexions intergroupes ;
- J_V : max des P(couverture < τ_V) sur États et scénarios S1/S2A, sous le régime du run ;
- J_G : part des liens fonctionnels (toute la population) coupés par les frontières d'État ;
- J_R : risque (conflit, sécurité) — **UNKNOWN** : aucune donnée, jamais 0 ;
- J_T : coût de transition = part de la population qui change d'État (meilleur appariement) ;
- J_inst : coûts réels (02 §15) — surcoûts fixes par État (administration, sécurité non
  mutualisée), part mutualisée payée une fois, gestion des frontières ∝ longueur ; aucune
  pénalité abstraite au nombre d'États (§42) ;
- J_reif : borne haute du risque de réification par rapport au statu quo.

La géométrie candidate reçoit le gabarit institutionnel du statu quo : États au
niveau supérieur, juridictions locales = districts du statu quo découpés par les
nouveaux États (emboîtement garanti).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from scipy import sparse

from amtgo.causal.library import CausalAnswer
from amtgo.core.channels import FragChannel, IntegChannel
from amtgo.domination.engine import domination
from amtgo.fragmentation.engine import fragmentation
from amtgo.geo.multiscale import transfer_distance
from amtgo.geo.partition import Partition, PartitionLevel
from amtgo.identity.state import BoundedSalienceResponse, SocialState
from amtgo.institutions.competences import Institution
from amtgo.institutions.composer import Configuration, institutionalization
from amtgo.institutions.regimes import ConstitutionalRegime
from amtgo.institutions.viability import FiscalUnion, Territory, ViabilityContext, ViabilityStatus, compute_viability
from amtgo.integration.engine import integration
from amtgo.manifests.normative import RightsThresholds

OBJECTIVES = ("J_D", "J_F", "J_conn", "J_V", "J_G", "J_R", "J_T", "J_inst", "J_reif")
UNKNOWN_OBJECTIVES = ("J_R",)


def candidate_partition(assign: np.ndarray, sq: Partition, regime_border: Any) -> Partition:
    """États candidats + juridictions locales = districts du statu quo ∩ États candidats."""
    local = sq.levels[1]
    pairs = sorted({(int(a), int(d)) for a, d in zip(assign, local.assignment, strict=True)})
    index = {p: k for k, p in enumerate(pairs)}
    loc = np.array([index[(int(a), int(d))] for a, d in zip(assign, local.assignment, strict=True)])
    n_states = int(assign.max()) + 1
    return Partition(sq.mesh_id, sq.cell_ids, [
        PartitionLevel(sq.levels[0].name, assign, [f"cand_{k}" for k in range(n_states)], regime_border),
        PartitionLevel(local.name, loc, [f"cand_{a}|{local.jurisdictions[d]}" for a, d in pairs], local.border)])


def functional_cut(kernel: sparse.csr_matrix, n: np.ndarray, assign: np.ndarray) -> float:
    coo = sparse.triu(kernel, k=1).tocoo()
    w = coo.data * n[coo.row] * n[coo.col]
    return float((w * (assign[coo.row] != assign[coo.col])).sum() / max(w.sum(), 1e-300))


def transition_share(assign: np.ndarray, baseline: np.ndarray, pop: np.ndarray) -> float:
    joint: dict[tuple[str, str], float] = defaultdict(float)
    for a, b, w in zip(assign, baseline, pop, strict=True):
        joint[(str(a), str(b))] += float(w)
    return transfer_distance(joint)


def border_length_km(edges: list[tuple[int, int, float]], assign: np.ndarray) -> float:
    return float(sum(length for i, j, length in edges if assign[i] != assign[j]))


def evaluate_geometry(state: SocialState, partition: Partition, institutions: dict[str, list[Institution]],
                      rights: RightsThresholds, weights: dict[IntegChannel, float],
                      salience: CausalAnswer, horizon_years: float, base_index: float) -> dict[str, Any]:
    """Objectifs dépendant de l'ontologie : J_D, J_F, J_conn, J_reif (et la contrainte de droits)."""
    dom = domination(state, partition, institutions, rights)
    frag = fragmentation(state, partition)
    integ = integration(state, partition, weights)
    pop_g = state.population.sum(axis=1).mean(axis=0)
    f_net = {f.group: f.value.mean for f in frag if f.channel is FragChannel.NETWORK and f.value is not None}
    index = institutionalization(state, partition, Configuration(institutions, []))
    reif = None
    if salience.known:
        iv = salience.interval()
        r = BoundedSalienceResponse(iv.lo, iv.hi, horizon_years, salience.reason).salience_response(
            index - base_index, horizon_years)
        reif = r.upper
    return {"J_D": max((d.p_exceed for d in dom), default=0.0),
            "J_F": float(sum(f_net.get(g, 0.0) * pop_g[i] for i, g in enumerate(state.groups)) / pop_g.sum()),
            "J_conn": None if integ.j_conn is None else float(integ.j_conn.mean or 0.0),
            "J_reif": reif,
            "violations": sorted({f"droits:{d.group}|{d.domain.value}" for d in dom if d.violation})}


def viability_objective(union: FiscalUnion, regime: ConstitutionalRegime,
                        contexts: dict[str, ViabilityContext], scenarios: dict[str, Any]) -> tuple[float | None, int]:
    """J_V = max P(couverture < τ) ; nombre d'États NOT_VIABLE (information, pas contrainte)."""
    worst, not_viable = 0.0, 0
    for sid, ctx in contexts.items():
        for t in union.territory_ids:
            a = compute_viability(Territory(t, "state"), regime, scenarios[sid], ctx)
            if a.status is ViabilityStatus.UNKNOWN or a.p_shortfall is None:
                return None, 0
            worst = max(worst, a.p_shortfall)
            not_viable += int(a.status is ViabilityStatus.NOT_VIABLE)
    return worst, not_viable


def institutional_cost(n_states: int, regime: ConstitutionalRegime, f_admin: float, f_sec: float,
                       border_km: float, cost_per_km: float) -> float:
    c = regime.defence_rules.common_defence_share
    return n_states * (f_admin + (1.0 - c) * f_sec) + c * f_sec + border_km * cost_per_km
