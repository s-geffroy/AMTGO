"""Fragmentation par canal (prompt §23, 02 §10).

    F^c_g = Σ_ij T^g_ijc · σ^{d(c)}_ij · (1 − μ^g_ijc)  /  Σ_ij T^g_ijc        ∈ [0,1]

avec T^g_ijc = R^c_ij · n_gi · n_gj les liens *valorisés* du groupe g dans le
canal c. La fragmentation mesure des **liens coupés**, jamais la présence d'un
groupe de part et d'autre d'une frontière : un groupe présent dans deux États
sans liens entre ses deux parties n'est pas fragmenté (prompt §23, monde F).

Pour le canal culturel, la cohésion est modulée par le partage d'identité
nationale quand celle-ci est connue (prompt §21).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import sparse

from amtgo.core.channels import FRAG_BORDER, FragChannel, IntegChannel
from amtgo.core.uncertainty import UncertainValue
from amtgo.geo.partition import BorderDim, Partition
from amtgo.identity.state import SocialState
from amtgo.infrastructure.hyperedges import Hyperedge


@dataclass(frozen=True)
class FragmentationEstimate:
    group: str
    channel: FragChannel
    value: UncertainValue | None  # None : UNKNOWN (canal sans données)


def cut_weights(kernel: sparse.csr_matrix, partition: Partition, channel: FragChannel | IntegChannel,
                border_dim: BorderDim, overlays: list[Hyperedge], group: str | None) -> sparse.csr_matrix:
    """Noyau pondéré par σ^{d(c)}_ij (1 − μ) : la part coupée de chaque lien."""
    coo = kernel.tocoo()
    sigma = partition.pair_strength(coo.row, coo.col, border_dim)
    factor = sigma.copy()
    for h in overlays:
        mu = h.mitigation.get(channel)
        if mu is None or (h.groups is not None and group not in h.groups):
            continue
        mask = h.member_mask(partition.cell_ids)
        both = mask[coo.row] & mask[coo.col]
        factor[both] *= 1.0 - mu
    return sparse.csr_matrix((coo.data * factor, (coo.row, coo.col)), shape=kernel.shape)


def _quadratic(kernel: sparse.csr_matrix, n: np.ndarray) -> np.ndarray:
    """nᵀ K n pour chaque tirage ; ``n`` (S, N) → (S,)."""
    return np.asarray(np.einsum("sn,ns->s", n, kernel @ n.T))


def _cultural_kernel(state: SocialState, g: int, base: sparse.csr_matrix) -> sparse.csr_matrix:
    if state.national_identity is None:
        return base
    nu = state.national_identity[:, g, :]  # (N, K)
    coo = base.tocoo()
    affinity = np.einsum("ek,ek->e", nu[coo.row], nu[coo.col])  # P(même identité nationale)
    return sparse.csr_matrix((coo.data * affinity, (coo.row, coo.col)), shape=base.shape)


def fragmentation(state: SocialState, partition: Partition, overlays: list[Hyperedge] | None = None
                  ) -> list[FragmentationEstimate]:
    overlays = overlays or []
    out = []
    for c in FragChannel:
        for gi, g in enumerate(state.groups):
            kernel = state.group_ties.get((c, g), state.ties.get(c))
            if kernel is None:
                out.append(FragmentationEstimate(g, c, None))
                continue
            if c is FragChannel.CULTURAL:
                kernel = _cultural_kernel(state, gi, kernel)
            n = state.population[:, :, gi]
            den = _quadratic(kernel, n)
            num = _quadratic(cut_weights(kernel, partition, c, FRAG_BORDER[c], overlays, g), n)
            ratio = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
            out.append(FragmentationEstimate(g, c, UncertainValue.from_samples(np.clip(ratio, 0.0, 1.0))))
    return out
