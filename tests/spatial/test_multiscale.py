"""M2 : opérations multi-échelles — conservation et distance de partitions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from shapely.geometry import box

from amtgo.core.enums import EvidenceStatus, PrivacyClass, SupportType
from amtgo.core.quality import QualityVector
from amtgo.core.uncertainty import UncertainValue
from amtgo.data.observations import Observation
from amtgo.geo.mesh import BBoxExtent, Mesh, MeshDefinition, MeshFamily
from amtgo.geo.multiscale import (
    PartitionMetric,
    area_weighted_transfer,
    coverage_ratio,
    partition_distance,
)
from amtgo.geo.ops import create_base_mesh, refine_mesh
from amtgo.geo.support import allocate_point_masses

BBOX = (-25.0, -26.0, -23.0, -24.0)
Q = QualityVector(source_reliability=1, spatial_precision=1, temporal_precision=1, construct_validity=1,
                  representativeness=1, license_usability=1, privacy_usability=1)


def _mesh(family: MeshFamily, res: int, mid: str) -> Mesh:
    d = MeshDefinition(mesh_id=mid, family=family, resolution=res, extent=BBoxExtent(bbox=BBOX),
                       grid_base_km=400 if family is MeshFamily.GRID_LAEA else None)
    return create_base_mesh(d, box(*BBOX))


@pytest.fixture(scope="module")
def grid() -> Mesh:
    return _mesh(MeshFamily.GRID_LAEA, 4, "grid")


@pytest.fixture(scope="module")
def hexes() -> Mesh:
    return _mesh(MeshFamily.H3, 4, "hex")


def test_transfer_conserves_mass_exact_nesting(grid: Mesh) -> None:
    fine = refine_mesh(grid, "fine")
    values = {cid: float(i + 1) for i, cid in enumerate(grid.cell_ids)}
    t = area_weighted_transfer(values, grid, fine)
    assert t.total_out == pytest.approx(t.total_in, rel=1e-9)
    assert t.unallocated == pytest.approx(0.0, abs=1e-6)
    back = area_weighted_transfer(t.values, fine, grid)
    for cid, v in values.items():
        assert back.values[cid] == pytest.approx(v, rel=1e-6)


def test_transfer_across_families_reports_loss(grid: Mesh, hexes: Mesh) -> None:
    values = {cid: 10.0 for cid in grid.cell_ids}
    t = area_weighted_transfer(values, grid, hexes)
    # Les bords ne coïncident pas : la masse perdue est rapportée, jamais redistribuée.
    assert t.total_out + t.unallocated == pytest.approx(t.total_in, rel=1e-9)
    assert t.unallocated >= 0


@pytest.mark.parametrize("metric", list(PartitionMetric))
def test_partition_distance_identity(grid: Mesh, metric: PartitionMetric) -> None:
    ref = refine_mesh(grid, "ref")
    labels = {cid: "west" if grid.cells[cid].geometry.centroid.x < -24 else "east" for cid in grid.cells}
    assert partition_distance(labels, grid, labels, grid, ref, metric).distance == pytest.approx(0.0, abs=1e-12)
    # Renommer les étiquettes ne change rien : seule la partition compte.
    renamed = {k: {"west": "A", "east": "B"}[v] for k, v in labels.items()}
    assert partition_distance(labels, grid, renamed, grid, ref, metric).distance == pytest.approx(0.0, abs=1e-12)


def test_partition_distance_same_split_other_family(grid: Mesh, hexes: Mesh) -> None:
    """Même découpage est-ouest porté par deux zonages : seuls les bords diffèrent."""
    ref = refine_mesh(grid, "ref")
    la = {c: "w" if grid.cells[c].geometry.centroid.x < -24 else "e" for c in grid.cells}
    lb = {c: "w" if hexes.cells[c].geometry.centroid.x < -24 else "e" for c in hexes.cells}
    lc = {c: "s" if hexes.cells[c].geometry.centroid.y < -25 else "n" for c in hexes.cells}
    same = partition_distance(la, grid, lb, hexes, ref).distance
    orthogonal = partition_distance(la, grid, lc, hexes, ref).distance
    assert 0.0 <= same < 0.15  # moins de 15 % de la surface réaffectée
    assert orthogonal > 0.35  # ~0.5 = maximum pour deux partitions binaires
    # La VI normalisée ordonne de même, mais pénalise beaucoup plus les bords (ADR-0007).
    vi_same = partition_distance(la, grid, lb, hexes, ref, PartitionMetric.VI).distance
    vi_orth = partition_distance(la, grid, lc, hexes, ref, PartitionMetric.VI).distance
    assert vi_same < vi_orth and vi_same > same


def test_coverage_ratio_exact(grid: Mesh, hexes: Mesh) -> None:
    for m in (grid, hexes):
        assert coverage_ratio(m) == pytest.approx(1.0, rel=1e-3)


def test_transfer_across_families_conserves_inside_domain(grid: Mesh, hexes: Mesh) -> None:
    values = {cid: 10.0 for cid in grid.cell_ids}
    t = area_weighted_transfer(values, grid, hexes)
    # Écart relatif ~1e-5 : densification des arêtes avant projection (geo.crs).
    assert t.unallocated == pytest.approx(0.0, abs=1e-4 * t.total_in)


def _pt(x: float, y: float, mass: float, disp: float | None) -> Observation:
    t = datetime(2025, 1, 1, tzinfo=UTC)
    return Observation(
        id=Observation.make_id("s", "pop", f"{x},{y}", t), source_id="s", variable_id="pop",
        support_type=SupportType.UNCERTAIN_POINT if disp else SupportType.POINT,
        geometry_wkt=f"POINT ({x} {y})", displacement_km=disp, valid_from=t, recorded_at=t,
        value=UncertainValue.exact(mass), quality=Q, evidence_status=EvidenceStatus.DIRECT,
        sensitivity=PrivacyClass.PUBLIC)


def test_geomasked_point_spreads(grid: Mesh) -> None:
    exact = allocate_point_masses([_pt(-24.0, -25.0, 100.0, None)], grid)
    masked = allocate_point_masses([_pt(-24.0, -25.0, 100.0, 30.0)], grid)
    assert len(exact.values) == 1
    assert len(masked.values) > 1  # pas de point-in-polygon naïf (03 §6)
    assert sum(masked.values.values()) + masked.unallocated == pytest.approx(100.0)


def test_point_outside_is_unallocated(grid: Mesh) -> None:
    a = allocate_point_masses([_pt(0.0, 0.0, 50.0, None)], grid)
    assert a.unallocated == pytest.approx(50.0) and not a.values
