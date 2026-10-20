"""M2 : invariants des maillages H3 et grille LAEA (prompt §15, §85)."""

from __future__ import annotations

import pytest
from shapely.geometry import box

from amtgo.errors import TopologyError
from amtgo.geo.crs import area_km2
from amtgo.geo.mesh import BBoxExtent, MeshDefinition, MeshFamily, assert_valid_mesh
from amtgo.geo.ops import (
    children,
    coarsen_mesh,
    create_base_mesh,
    neighbor_graph,
    neighbors,
    parent,
    refine_mesh,
)

BBOX = (-25.0, -26.0, -23.0, -24.0)  # océan, monde synthétique


def _def(family: MeshFamily, res: int, mesh_id: str = "mesh") -> MeshDefinition:
    return MeshDefinition(
        mesh_id=mesh_id, family=family, resolution=res, extent=BBoxExtent(bbox=BBOX),
        grid_base_km=400 if family is MeshFamily.GRID_LAEA else None,
    )


PARAMS = [(MeshFamily.H3, 4), (MeshFamily.GRID_LAEA, 4)]


@pytest.mark.parametrize("family,res", PARAMS)
def test_valid_and_non_overlapping(family: MeshFamily, res: int) -> None:
    mesh = create_base_mesh(_def(family, res), box(*BBOX))
    assert len(mesh) > 10
    assert_valid_mesh(mesh)


@pytest.mark.parametrize("family,res", PARAMS)
def test_deterministic(family: MeshFamily, res: int) -> None:
    a = create_base_mesh(_def(family, res), box(*BBOX))
    b = create_base_mesh(_def(family, res), box(*BBOX))
    assert a.cell_ids == b.cell_ids == sorted(a.cell_ids)
    assert a.cells_hash == b.cells_hash


@pytest.mark.parametrize("family,res", PARAMS)
def test_union_equals_extent(family: MeshFamily, res: int) -> None:
    """Couverture exacte : aucune bande non couverte au bord (règle intersecte + découpe)."""
    from amtgo.geo.crs import to_equal_area

    extent = box(*BBOX)
    mesh = create_base_mesh(_def(family, res), extent)
    assert mesh.total_area_km2 == pytest.approx(to_equal_area(extent).area / 1e6, rel=1e-3)
    assert any(c.clipped for c in mesh.cells.values())
    assert not all(c.clipped for c in mesh.cells.values())
    for c in mesh.cells.values():
        # ~1 m de tolérance : flèche entre deux points de densification (geo.crs).
        assert extent.buffer(1e-5).contains(c.geometry)


@pytest.mark.parametrize("family,res", PARAMS)
def test_thin_extent_still_covered(family: MeshFamily, res: int) -> None:
    """Une emprise plus fine qu'une cellule est couverte, pas ignorée."""
    thin = box(-24.5, -25.0, -24.45, -24.0)
    mesh = create_base_mesh(_def(family, res), thin)
    assert len(mesh) >= 1
    assert_valid_mesh(mesh)


@pytest.mark.parametrize("family,res", PARAMS)
def test_neighbors_symmetric(family: MeshFamily, res: int) -> None:
    mesh = create_base_mesh(_def(family, res), box(*BBOX))
    g = neighbor_graph(mesh)
    for a, ns in g.items():
        assert a not in ns
        for b in ns:
            assert a in g[b]
            assert mesh.cells[a].geometry.buffer(1e-9).intersects(mesh.cells[b].geometry)


@pytest.mark.parametrize("family,res", PARAMS)
def test_parent_children_coherent(family: MeshFamily, res: int) -> None:
    mesh = create_base_mesh(_def(family, res), box(*BBOX))
    fine = refine_mesh(mesh, "fine")
    assert fine.definition.resolution == res + 1
    assert_valid_mesh(fine)
    for cid in mesh.cell_ids:
        kids = [ch for ch in children(mesh, cid) if ch in fine.cells]
        assert kids  # toute cellule du domaine a au moins un enfant dans le domaine
        for ch in kids:
            assert fine.cells[ch].parent_cell_id == cid
    coarse = coarsen_mesh(fine, "coarse")
    assert_valid_mesh(coarse)
    assert set(mesh.cell_ids) <= set(coarse.cell_ids)
    for cid in fine.cell_ids:
        assert parent(fine, cid) in coarse.cells


def test_grid_exact_nesting_and_area() -> None:
    mesh = create_base_mesh(_def(MeshFamily.GRID_LAEA, 3), box(*BBOX))
    fine = refine_mesh(mesh, "fine")
    assert fine.total_area_km2 == pytest.approx(mesh.total_area_km2, rel=1e-12)
    side = 400 / 2**3
    for c in mesh.cells.values():
        if not c.clipped:
            assert c.area_km2 == pytest.approx(side * side)
        # L'aire stockée (calculée en LAEA) concorde avec l'aire de la géométrie reprojetée.
        assert area_km2(c.geometry) == pytest.approx(c.area_km2, rel=1e-3)


def test_refined_meshes_cover_same_domain() -> None:
    for fam in (MeshFamily.H3, MeshFamily.GRID_LAEA):
        mesh = create_base_mesh(_def(fam, 4), box(*BBOX))
        fine = refine_mesh(mesh, "fine")
        assert fine.total_area_km2 == pytest.approx(mesh.total_area_km2, rel=1e-3)


def test_area_never_in_degrees() -> None:
    mesh = create_base_mesh(_def(MeshFamily.H3, 4), box(*BBOX))
    c = next(iter(mesh.cells.values()))
    # H3 r4 ≈ 1 770 km² ; une aire « en degrés² » serait < 1.
    assert 1000 < c.area_km2 < 2500


def test_unknown_cell_refused() -> None:
    mesh = create_base_mesh(_def(MeshFamily.GRID_LAEA, 3), box(*BBOX))
    with pytest.raises(TopologyError):
        neighbors(mesh, "g3_999_999")


def test_empty_extent_refused() -> None:
    with pytest.raises(TopologyError):
        create_base_mesh(_def(MeshFamily.H3, 4), box(0, 0, 0, 0))


def test_definition_validation() -> None:
    with pytest.raises(ValueError):
        MeshDefinition(mesh_id="xx", family=MeshFamily.GRID_LAEA, resolution=1, extent=BBoxExtent(bbox=BBOX))
    with pytest.raises(ValueError):
        BBoxExtent(bbox=(10, 0, 5, 1))
