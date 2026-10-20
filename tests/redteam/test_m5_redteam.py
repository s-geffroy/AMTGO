"""Red-team M5 : présence ≠ fragmentation, pas de D réalisé inventé, mondes A–F."""

from __future__ import annotations

import numpy as np

from amtgo.core.channels import FragChannel, IntegChannel
from amtgo.fragmentation.engine import fragmentation
from amtgo.manifests.normative import RightsThresholds
from amtgo.validation import worlds as W
from amtgo.validation.worlds_report import checks, evaluate_all

RIGHTS = RightsThresholds(severe_domination_threshold=0.5, severe_domination_probability_max=0.05,
                          urgent_domination_threshold=0.7, urgent_probability=0.5)
WEIGHTS = {c: 1.0 for c in IntegChannel}


def test_all_world_properties_hold() -> None:
    failed = [(t, v) for t, ok, v in checks(evaluate_all(RIGHTS, WEIGHTS)) if not ok]
    assert not failed, failed


def test_presence_on_both_sides_is_not_fragmentation() -> None:
    """prompt §23 : un groupe présent dans deux États, sans liens entre ses parties, n'est pas fragmenté."""
    lat = W.Lattice(10, 4)
    x = lat.xy[:, 0] / W.SPACING_KM
    st = W.world_a().state
    pop = np.full((20, lat.n, 1), 100.0)
    k = lat.distance_kernel().tocoo()
    cross = (x[k.row] < 5) != (x[k.col] < 5)
    data = k.data.copy()
    data[cross] = 0.0  # aucun lien à travers la frontière
    from scipy import sparse

    from amtgo.identity.state import SocialState

    st = SocialState("o", lat.ids, ["x"], pop,
                     ties={FragChannel.NETWORK: sparse.csr_matrix((data, (k.row, k.col)), shape=(lat.n, lat.n))})
    for f in fragmentation(st, lat.bands([5])):
        assert f.value is None or f.value.mean == 0.0


def test_no_territorial_channel_without_attachment() -> None:
    for name in ("A", "B", "D", "F"):
        w = W.WORLDS[name]()
        probe = next(iter(w.probes.values()))
        for f in fragmentation(w.state, probe):
            if f.channel is FragChannel.TERRITORIAL:
                assert f.value is None, f"monde {name} : canal territorial sans attachement"
