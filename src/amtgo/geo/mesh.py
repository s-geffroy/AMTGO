"""Maillages analytiques (prompt §15, M2).

Les cellules sont des unités d'*analyse*, jamais des unités juridiques (02 §2).
Deux familles (ADR-0007) : ``h3`` (hexagones, imbrication approximative) et
``grid_laea`` (carrés dans la projection équivalente, imbrication exacte).
Avoir deux *formes* de zonage — et pas seulement deux résolutions — est ce que
demande le MAUP.

Règle d'appartenance commune : une cellule fait partie du maillage si elle
intersecte l'emprise, et sa géométrie est découpée sur l'emprise. L'union des
cellules égale l'emprise (invariant testé) : deux maillages couvrent exactement
le même domaine, et aucune masse ne se perd au bord.

Déterminisme : à définition égale, mêmes identifiants, même ordre, même
empreinte (``cells_hash``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from amtgo.errors import TopologyError
from amtgo.utils.canonical import content_hash, sha256_hex


class MeshFamily(StrEnum):
    H3 = "h3"
    GRID_LAEA = "grid_laea"


class BBoxExtent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["bbox"] = "bbox"
    bbox: tuple[float, float, float, float]

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        minx, miny, maxx, maxy = self.bbox
        if not (-180 <= minx < maxx <= 180 and -90 <= miny < maxy <= 90):
            raise ValueError(f"bbox invalide : {self.bbox}")
        return self


class SourceUnionExtent(BaseModel):
    """Emprise = union des géométries d'une variable d'une source ingérée (traçable)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["source_union"] = "source_union"
    source_id: str
    variable_id: str


class MeshDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mesh_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")
    family: MeshFamily
    resolution: int = Field(ge=0, le=15)
    extent: BBoxExtent | SourceUnionExtent = Field(discriminator="kind")
    version: str = "1"
    # grid_laea uniquement : côté (km) au niveau 0 ; côté au niveau L = base / 2**L.
    grid_base_km: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _family_params(self) -> Self:
        if self.family is MeshFamily.GRID_LAEA and self.grid_base_km is None:
            raise ValueError("grid_laea exige grid_base_km")
        if self.family is MeshFamily.H3 and self.grid_base_km is not None:
            raise ValueError("grid_base_km n'a pas de sens pour h3")
        return self

    @property
    def definition_hash(self) -> str:
        return content_hash(self)

    def with_resolution(self, resolution: int, mesh_id: str) -> MeshDefinition:
        return self.model_copy(update={"resolution": resolution, "mesh_id": mesh_id})


@dataclass(frozen=True)
class Cell:
    cell_id: str
    resolution: int
    geometry: Polygon | MultiPolygon  # EPSG:4326, découpée sur l'emprise si clipped
    area_km2: float  # calculée en projection équivalente
    parent_cell_id: str | None
    clipped: bool = False


class FamilyOps(Protocol):
    """Opérations propres à une famille de maillage."""

    def candidate_ids(self, definition: MeshDefinition, extent: BaseGeometry) -> set[str]: ...

    def build_cells(
        self, definition: MeshDefinition, ids: Iterable[str], extent: BaseGeometry
    ) -> list[Cell]: ...

    def neighbor_ids(self, definition: MeshDefinition, cell_id: str) -> set[str]: ...

    def parent_id(self, definition: MeshDefinition, cell_id: str) -> str | None: ...

    def child_ids(self, definition: MeshDefinition, cell_id: str) -> list[str]: ...

    def exact_nesting(self) -> bool: ...


@dataclass
class Mesh:
    definition: MeshDefinition
    extent: BaseGeometry
    cells: dict[str, Cell] = field(default_factory=dict)

    @property
    def mesh_id(self) -> str:
        return self.definition.mesh_id

    @property
    def cell_ids(self) -> list[str]:
        return list(self.cells)

    def __len__(self) -> int:
        return len(self.cells)

    @property
    def cells_hash(self) -> str:
        """Empreinte déterministe : identifiants, parents et géométries (WKT arrondi à 1e-9°)."""
        from shapely import wkt

        parts = []
        for cid in sorted(self.cells):
            c = self.cells[cid]
            parts.append(
                f"{cid}|{c.parent_cell_id}|{int(c.clipped)}|{wkt.dumps(c.geometry, rounding_precision=9)}"
            )
        return "sha256:" + sha256_hex("\n".join(parts))

    @property
    def total_area_km2(self) -> float:
        return sum(c.area_km2 for c in self.cells.values())

    def union(self) -> BaseGeometry:
        return unary_union([c.geometry for c in self.cells.values()])


def _sorted_cells(cells: Iterable[Cell]) -> dict[str, Cell]:
    return {c.cell_id: c for c in sorted(cells, key=lambda c: c.cell_id)}


def bbox_geometry(extent: BBoxExtent) -> Polygon:
    return box(*extent.bbox)


# Tolérances numériques des invariants (arithmétique flottante, densification des arêtes).
OVERLAP_TOLERANCE_KM2 = 1e-6
COVERAGE_REL_TOLERANCE = 1e-3


def assert_valid_mesh(mesh: Mesh, overlap_tolerance_km2: float = OVERLAP_TOLERANCE_KM2) -> None:
    """Invariants topologiques (prompt §85).

    Géométries valides, aires positives, non-recouvrement au même niveau, et
    couverture : la surface de l'union égale celle de l'emprise.
    """
    from shapely.strtree import STRtree

    from amtgo.geo.crs import to_equal_area

    if not mesh.cells:
        raise TopologyError(f"{mesh.mesh_id} : maillage vide")
    geoms = []
    for c in mesh.cells.values():
        if not c.geometry.is_valid or c.geometry.is_empty:
            raise TopologyError(f"{mesh.mesh_id}/{c.cell_id} : géométrie invalide")
        if c.area_km2 <= 0:
            raise TopologyError(f"{mesh.mesh_id}/{c.cell_id} : aire non positive")
        if c.resolution != mesh.definition.resolution:
            raise TopologyError(f"{mesh.mesh_id}/{c.cell_id} : résolution incohérente")
        geoms.append(to_equal_area(c.geometry))
    tree = STRtree(geoms)
    left, right = tree.query(geoms, predicate="intersects")
    ids = list(mesh.cells)
    for i, j in zip(left, right, strict=True):
        if i >= j:
            continue
        overlap_km2 = geoms[i].intersection(geoms[j]).area / 1e6
        if overlap_km2 > overlap_tolerance_km2:
            raise TopologyError(
                f"{mesh.mesh_id} : {ids[i]} et {ids[j]} se chevauchent ({overlap_km2:.3g} km²)"
            )
    extent_km2 = to_equal_area(mesh.extent).area / 1e6
    covered_km2 = sum(g.area for g in geoms) / 1e6
    if abs(covered_km2 - extent_km2) > COVERAGE_REL_TOLERANCE * extent_km2:
        raise TopologyError(
            f"{mesh.mesh_id} : couverture {covered_km2:.1f} km² ≠ emprise {extent_km2:.1f} km²"
        )
