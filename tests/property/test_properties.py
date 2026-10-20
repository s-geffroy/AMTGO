"""Tests par propriétés (hypothesis) sur les invariants mathématiques (prompt §84)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import box

from amtgo.core.uncertainty import UncertainValue
from amtgo.geo.mesh import BBoxExtent, MeshDefinition, MeshFamily
from amtgo.geo.multiscale import PartitionMetric, area_weighted_transfer, partition_distance
from amtgo.geo.ops import create_base_mesh, refine_mesh

finite = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


@given(st.lists(finite, min_size=1, max_size=200), finite, finite)
def test_exceedance_is_probability_and_monotone(samples: list[float], t1: float, t2: float) -> None:
    u = UncertainValue.from_samples(samples)
    lo, hi = sorted((t1, t2))
    p_lo, p_hi = u.exceedance_probability(lo), u.exceedance_probability(hi)
    assert 0.0 <= p_hi <= p_lo <= 1.0


@given(st.lists(st.floats(min_value=0, max_value=1), min_size=2, max_size=100))
def test_unit_samples_stay_in_unit_interval(samples: list[float]) -> None:
    assert UncertainValue.from_samples(samples).is_within(0.0, 1.0)


@given(st.lists(finite, min_size=1, max_size=100), st.floats(min_value=0.01, max_value=0.99))
def test_cvar_at_least_mean(samples: list[float], alpha: float) -> None:
    u = UncertainValue.from_samples(samples)
    assert u.cvar(alpha) >= (u.mean or 0.0) - 1e-6 * max(1.0, abs(u.mean or 0.0))


_BBOX = (-25.0, -26.0, -24.0, -25.0)
_GRID = create_base_mesh(
    MeshDefinition(mesh_id="gp", family=MeshFamily.GRID_LAEA, resolution=4, grid_base_km=400,
                   extent=BBoxExtent(bbox=_BBOX)), box(*_BBOX))
_FINE = refine_mesh(_GRID, "fp")
_IDS = _GRID.cell_ids


@settings(max_examples=30, deadline=None)
@given(st.lists(st.floats(min_value=0, max_value=1e5), min_size=len(_IDS), max_size=len(_IDS)))
def test_transfer_conserves_total(vals: list[float]) -> None:
    values = dict(zip(_IDS, vals, strict=True))
    t = area_weighted_transfer(values, _GRID, _FINE)
    assert t.total_out + t.unallocated == pytest.approx(sum(vals), rel=1e-9, abs=1e-6)


@settings(max_examples=30, deadline=None)
@given(st.lists(st.sampled_from("abc"), min_size=len(_IDS), max_size=len(_IDS)),
       st.lists(st.sampled_from("xyz"), min_size=len(_IDS), max_size=len(_IDS)),
       st.sampled_from(list(PartitionMetric)))
def test_partition_distance_bounded_and_symmetric(la: list[str], lb: list[str],
                                                  metric: PartitionMetric) -> None:
    a = dict(zip(_IDS, la, strict=True))
    b = dict(zip(_IDS, lb, strict=True))
    d_ab = partition_distance(a, _GRID, b, _GRID, _FINE, metric).distance
    d_ba = partition_distance(b, _GRID, a, _GRID, _FINE, metric).distance
    assert 0.0 <= d_ab <= 1.0
    assert d_ab == pytest.approx(d_ba, abs=1e-12)
