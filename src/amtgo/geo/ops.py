"""API de maillage minimale du prompt §15.

``create_base_mesh``, ``refine_mesh``, ``coarsen_mesh``, ``neighbors``,
``parent``, ``children``. Toutes déterministes.
"""

from __future__ import annotations

from shapely.geometry.base import BaseGeometry

from amtgo.errors import TopologyError
from amtgo.geo.families import ops_for
from amtgo.geo.mesh import Mesh, MeshDefinition, _sorted_cells


def create_base_mesh(definition: MeshDefinition, extent: BaseGeometry) -> Mesh:
    """Cellules de ``definition`` qui intersectent ``extent`` (EPSG:4326), découpées sur elle."""
    if extent.is_empty or not extent.is_valid or extent.area == 0:
        raise TopologyError(f"{definition.mesh_id} : emprise vide ou invalide")
    fam = ops_for(definition)
    cells = fam.build_cells(definition, fam.candidate_ids(definition, extent), extent)
    if not cells:
        raise TopologyError(f"{definition.mesh_id} : aucune cellule dans l'emprise")
    return Mesh(definition, extent, _sorted_cells(cells))


def refine_mesh(mesh: Mesh, mesh_id: str) -> Mesh:
    """Maillage enfant uniforme : chaque cellule remplacée par ses enfants.

    Le raffinement *adaptatif* (07 §7, selon l'hétérogénéité des champs) exige
    les champs latents de M3 ; il n'est pas implémenté ici.
    """
    res = mesh.definition.resolution + 1
    definition = mesh.definition.with_resolution(res, mesh_id)
    fam = ops_for(definition)
    child_ids = {c for cid in mesh.cells for c in fam.child_ids(mesh.definition, cid)}
    if not fam.exact_nesting():
        # H3 : des enfants de cellules voisines peuvent intersecter l'emprise.
        child_ids |= fam.candidate_ids(definition, mesh.extent)
    cells = fam.build_cells(definition, child_ids, mesh.extent)
    return Mesh(definition, mesh.extent, _sorted_cells(cells))


def coarsen_mesh(mesh: Mesh, mesh_id: str) -> Mesh:
    """Maillage parent : ensemble des parents des cellules."""
    if mesh.definition.resolution == 0:
        raise TopologyError(f"{mesh.mesh_id} : déjà au niveau 0")
    res = mesh.definition.resolution - 1
    definition = mesh.definition.with_resolution(res, mesh_id)
    fam = ops_for(definition)
    parent_ids = {p for cid in mesh.cells if (p := fam.parent_id(mesh.definition, cid))}
    if not fam.exact_nesting():
        parent_ids |= fam.candidate_ids(definition, mesh.extent)
    cells = fam.build_cells(definition, parent_ids, mesh.extent)
    return Mesh(definition, mesh.extent, _sorted_cells(cells))


def _require(mesh: Mesh, cell_id: str) -> None:
    if cell_id not in mesh.cells:
        raise TopologyError(f"{cell_id} n'appartient pas à {mesh.mesh_id}")


def neighbors(mesh: Mesh, cell_id: str) -> list[str]:
    """Voisins par arête *dans le domaine*, triés.

    Candidats de l'index (H3 ou grille), présents dans le maillage, et dont la
    géométrie — éventuellement découpée — partage avec la cellule une frontière
    de longueur positive. Deux hexagones adjacents dans l'index mais séparés par
    le bord de l'emprise ne sont pas voisins.
    """
    _require(mesh, cell_id)
    geom = mesh.cells[cell_id].geometry
    out = []
    for n in ops_for(mesh.definition).neighbor_ids(mesh.definition, cell_id):
        other = mesh.cells.get(n)
        if other is not None and geom.intersection(other.geometry).length > 0:
            out.append(n)
    return sorted(out)


def parent(mesh: Mesh, cell_id: str) -> str | None:
    _require(mesh, cell_id)
    return mesh.cells[cell_id].parent_cell_id


def children(mesh: Mesh, cell_id: str) -> list[str]:
    """Identifiants des enfants au niveau suivant (indépendamment d'un maillage raffiné)."""
    _require(mesh, cell_id)
    return ops_for(mesh.definition).child_ids(mesh.definition, cell_id)


def neighbor_graph(mesh: Mesh) -> dict[str, list[str]]:
    return {cid: neighbors(mesh, cid) for cid in mesh.cells}
