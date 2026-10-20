"""Risque de réification (prompt §19, 02 §12).

    RRI(G) = E[S^id_{t+H}(G) − S^id_{t+H}(baseline)]

Une architecture qui aligne ses frontières sur un clivage risque de renforcer la
saillance de ce clivage — et de produire ensuite sa propre justification (01 §2).

L'**alignement** d'une partition sur les groupes est mesuré par l'indice de
dissimilarité multigroupe (descriptif, ∈ [0,1]) au niveau le plus élevé de la
partition. Il sert ici à *signaler* un risque, jamais à être maximisé.

La traduction alignement → saillance exige un effet causal (M7). Sans lui :
CAUSAL_EFFECT_UNKNOWN ; avec des bornes exploratoires déclarées : un intervalle.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from amtgo.core.uncertainty import UncertainValue
from amtgo.errors import CausalUnsupported
from amtgo.geo.partition import Partition
from amtgo.identity.state import IdentityTransition, SocialState


def alignment(state: SocialState, partition: Partition, level: int = 0) -> UncertainValue:
    """Dissimilarité multigroupe des juridictions du niveau ``level`` (tirages)."""
    lv = partition.levels[level]
    n = state.population  # (S, N, G)
    per_k = np.stack([n[:, lv.assignment == k, :].sum(axis=1) for k in range(len(lv.jurisdictions))],
                     axis=1)  # (S, K, G)
    tot_k = per_k.sum(axis=2)  # (S, K)
    tot = tot_k.sum(axis=1)  # (S,)
    p_gk = np.divide(per_k, tot_k[:, :, None], out=np.zeros_like(per_k), where=tot_k[:, :, None] > 0)
    p_g = per_k.sum(axis=1) / tot[:, None]  # (S, G)
    interaction = (p_g * (1 - p_g)).sum(axis=1)
    num = (tot_k[:, :, None] * np.abs(p_gk - p_g[:, None, :])).sum(axis=(1, 2))
    d = np.divide(num, 2 * tot * interaction, out=np.zeros_like(num), where=interaction > 0)
    return UncertainValue.from_samples(np.clip(d, 0.0, 1.0))


def reification_risk(state: SocialState, solution: Partition, baseline: Partition,
                     horizon_years: float, transition: IdentityTransition) -> dict[str, Any]:
    """Signature du prompt §19 : ``reification_risk(solution, baseline, horizon)``."""
    a_sol, a_base = alignment(state, solution), alignment(state, baseline)
    assert a_sol.mean is not None and a_base.mean is not None
    delta = a_sol.mean - a_base.mean
    try:
        rri = transition.salience_response(delta, horizon_years)
        status = "BOUNDED"
    except CausalUnsupported as exc:
        rri, status = None, f"CAUSAL_EFFECT_UNKNOWN ({exc})"
    return {"alignment_solution": a_sol, "alignment_baseline": a_base, "delta_alignment": delta,
            "rri": rri, "status": status, "horizon_years": horizon_years}
