"""Tenseur d'intégration et coût de rupture des connexions valorisées (prompt §24, 02 §11).

Par canal c et paire de groupes (a, b) :
- exposition X^c_ab = Σ_ij R^c_ij n_ai n_bj (contact intergroupe) ;
- qualité Q^c_ab ∈ [0,1] (déclarée ou mesurée ; sinon UNKNOWN) ;
- réciprocité = min(X_ab, X_ba) / max(X_ab, X_ba) ;
- connexion valorisée I^{c,+}_ab = X^c_ab Q^c_ab.

    J_conn = Σ_c κ_c Σ_{a≠b} Q^c_ab Σ_ij R^c_ij n_ai n_bj σ^{d(c)}_ij (1 − μ)
             / Σ_c κ_c Σ_{a,b} X^c_ab                                             ∈ [0,1]

soit la part de **toute** la vie sociale (contacts intra- et intergroupes) qui est
une connexion intergroupe valorisée coupée par la géométrie. C'est une somme au
sens de 02 §11, rapportée à une échelle commune.

Révision M5 : la première version divisait par les seules connexions
intergroupes. Elle classait alors à l'envers deux populations séparées (A : les
rares contacts sont tous à la frontière, « 84 % coupés ») et deux populations
intégrées (B : « 9 % coupés » d'un volume immense) — ADR-0017.

Les poids κ_c sont normatifs (manifeste). Aucun score unique ne sert de
primitive : le tenseur par canal est conservé.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from amtgo.core.channels import INTEG_BORDER, IntegChannel
from amtgo.core.uncertainty import UncertainValue
from amtgo.fragmentation.engine import cut_weights
from amtgo.geo.partition import Partition
from amtgo.identity.state import SocialState
from amtgo.infrastructure.hyperedges import Hyperedge


@dataclass(frozen=True)
class IntegrationResult:
    channels: dict[IntegChannel, dict[str, Any]]  # par canal : exposition, qualité, réciprocité, part coupée
    j_conn: UncertainValue | None  # None : aucun canal évaluable
    unknown_channels: list[IntegChannel]


def _cross(kernel: Any, n: np.ndarray) -> np.ndarray:
    """(S, G, G) : Σ_ij K_ij n_ai n_bj pour chaque tirage."""
    s, _, g = n.shape
    out = np.zeros((s, g, g))
    for b in range(g):
        kb = kernel @ n[:, :, b].T  # (N, S)
        out[:, :, b] = np.einsum("sna,ns->sa", n, kb)
    return out


def integration(state: SocialState, partition: Partition, weights: dict[IntegChannel, float],
                overlays: list[Hyperedge] | None = None) -> IntegrationResult:
    overlays = overlays or []
    g = len(state.groups)
    off = ~np.eye(g, dtype=bool)
    channels: dict[IntegChannel, dict[str, Any]] = {}
    unknown: list[IntegChannel] = []
    num_total = np.zeros(state.n_samples)
    den_total = np.zeros(state.n_samples)
    for c in IntegChannel:
        kernel = state.exposure.get(c)
        q = state.quality.get(c)
        if kernel is None or q is None:
            unknown.append(c)
            continue
        x = _cross(kernel, state.population)
        cut = _cross(cut_weights(kernel, partition, c, INTEG_BORDER[c], overlays, None), state.population)
        valued, valued_cut = (x * q)[:, off].sum(axis=1), (cut * q)[:, off].sum(axis=1)
        all_contact = x.sum(axis=(1, 2))
        xm = x.mean(axis=0)
        recip = np.divide(np.minimum(xm, xm.T), np.maximum(xm, xm.T), out=np.ones_like(xm),
                          where=np.maximum(xm, xm.T) > 0)
        share = np.divide(valued_cut, valued, out=np.zeros_like(valued), where=valued > 0)
        intergroup = np.divide(x[:, off].sum(axis=1), all_contact, out=np.zeros_like(all_contact),
                               where=all_contact > 0)
        channels[c] = {"exposure_mean": xm.tolist(), "quality": q.tolist(), "reciprocity": recip.tolist(),
                       "intergroup_share_of_contact": UncertainValue.from_samples(np.clip(intergroup, 0, 1)),
                       "cut_share_of_intergroup": UncertainValue.from_samples(np.clip(share, 0.0, 1.0))}
        k = weights.get(c, 0.0)
        num_total += k * valued_cut
        den_total += k * all_contact
    j = None
    if np.any(den_total > 0):
        j = UncertainValue.from_samples(np.clip(np.divide(num_total, den_total, out=np.zeros_like(num_total),
                                                          where=den_total > 0), 0.0, 1.0))
    return IntegrationResult(channels, j, unknown)
