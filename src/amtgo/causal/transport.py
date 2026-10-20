"""Transportabilité source → cible (04 §10) : recouvrement des modificateurs d'effet.

Recouvrement = part des unités cibles dont chaque modificateur d'effet est dans
le support observé de la source (quantiles 5–95 %). Un modificateur absent de la
cible n'est pas « supposé identique » : le transport est alors UNSUPPORTED.
"""

from __future__ import annotations

import numpy as np

from amtgo.causal.model import TransportStatus


def overlap(source: dict[str, np.ndarray], target: dict[str, np.ndarray]) -> float:
    if not source or set(source) - set(target):
        return 0.0
    inside = np.ones(len(next(iter(target.values()))), dtype=bool)
    for k, s in source.items():
        lo, hi = np.quantile(s, [0.05, 0.95])
        inside &= (target[k] >= lo) & (target[k] <= hi)
    return float(inside.mean())


def transport_status(overlap_score: float, identified_overlap: float, overlap_min: float) -> TransportStatus:
    if overlap_score >= identified_overlap:
        return TransportStatus.IDENTIFIED
    if overlap_score >= overlap_min:
        return TransportStatus.PARTIAL
    return TransportStatus.UNSUPPORTED
