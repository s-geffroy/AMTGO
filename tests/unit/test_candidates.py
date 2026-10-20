"""M8 : algorithmes de génération, contiguïté, manifeste du générateur."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError
from scipy import sparse

from amtgo.candidates.generate import (
    canonical_labels,
    community_partition,
    is_contiguous,
    repair_contiguity,
    spectral_partition,
    weighted_kmeans,
)
from amtgo.candidates.model import BASELINE_SCOPE, BASELINES, CandidateFamily, CandidateManifest


def _line(n: int) -> list[list[int]]:
    return [[j for j in (i - 1, i + 1) if 0 <= j < n] for i in range(n)]


def test_canonical_labels() -> None:
    assert canonical_labels(np.array([5, 5, 2, 9, 2])).tolist() == [0, 0, 1, 2, 1]


def test_weighted_kmeans_separates_and_is_deterministic() -> None:
    rng = np.random.default_rng(0)
    x = np.vstack([rng.normal(0, 1, (30, 2)), rng.normal(20, 1, (30, 2))])
    w = np.ones(60)
    a = weighted_kmeans(x, w, 2, 5, seed=1)
    assert np.array_equal(a, weighted_kmeans(x, w, 2, 5, seed=1))
    assert len(set(a[:30])) == 1 and len(set(a[30:])) == 1 and a[0] != a[-1]
    assert weighted_kmeans(x, w, 1, 5, seed=1).tolist() == [0] * 60  # union : un seul État


def _two_blocks() -> sparse.csr_matrix:
    k = np.zeros((20, 20))
    k[:10, :10] = 1.0
    k[10:, 10:] = 1.0
    k[9, 10] = k[10, 9] = 0.05
    return sparse.csr_matrix(k)


def test_spectral_cuts_weak_link() -> None:
    a = spectral_partition(_two_blocks(), np.ones(20), 2, 4, seed=0)
    assert len(set(a[:10])) == 1 and len(set(a[10:])) == 1 and a[0] != a[19]


def test_community_detection_cuts_weak_link() -> None:
    """Le lien faible (9–10) sépare toujours deux communautés ; la résolution règle leur nombre."""
    for r in (0.1, 1.0):
        a = community_partition(_line(20), _two_blocks(), np.ones(20), r, seed=0)
        assert a[9] != a[10]
    low = community_partition(_line(20), _two_blocks(), np.ones(20), 0.1, seed=0)
    high = community_partition(_line(20), _two_blocks(), np.ones(20), 3.0, seed=0)
    assert len(set(low)) <= len(set(high))


def test_repair_contiguity() -> None:
    adj = _line(6)
    split = np.array([0, 0, 1, 1, 0, 0])  # l'État 0 est coupé en deux
    assert not is_contiguous(split, adj)
    fixed, moved = repair_contiguity(split, adj, np.array([5.0, 5.0, 1.0, 1.0, 1.0, 1.0]))
    assert is_contiguous(fixed, adj) and moved == 2
    assert fixed.tolist() == [0, 0, 1, 1, 1, 1]  # la composante mineure rejoint son voisin


def test_island_is_a_geographic_fact() -> None:
    adj = [[1], [0], []]  # la cellule 2 est une île
    a = np.array([0, 0, 0])
    assert is_contiguous(a, adj)
    fixed, moved = repair_contiguity(a, adj, np.ones(3))
    assert moved == 0 and fixed.tolist() == [0, 0, 0]


def test_manifest_validation() -> None:
    base = dict(generator_id="g", version="1", description="d", level="state", reference_mesh="m",
                state_counts=[1, 2], restarts=2, community_resolutions=[1.0], network_kernel_length_km=10,
                network_kernel_cutoff=3)
    CandidateManifest.model_validate(base)
    for bad in ([0, 2], [2, 2]):
        with pytest.raises(ValidationError):
            CandidateManifest.model_validate(dict(base, state_counts=bad))
    with pytest.raises(ValidationError):  # aucune pénalité au nombre d'États ne peut être déclarée
        CandidateManifest.model_validate(dict(base, state_count_penalty=1.0))


def test_baselines_are_declared_with_scope() -> None:
    assert set(BASELINES) == {CandidateFamily.STATUS_QUO, CandidateFamily.NO_TERRITORIAL_CHANGE,
                              CandidateFamily.INSTITUTIONAL_ONLY_REFORM}
    assert all(f.is_baseline and f in BASELINE_SCOPE for f in BASELINES)
    assert not CandidateFamily.GEOGRAPHIC.is_baseline
