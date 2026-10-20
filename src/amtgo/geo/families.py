"""Implémentations des familles de maillage : H3 et grille carrée LAEA.

Règle d'appartenance commune (ADR-0007, révisée en M2) : une cellule appartient
au maillage si elle **intersecte** l'emprise, et sa géométrie est **découpée**
sur l'emprise. L'union des cellules égale donc l'emprise : aucune masse ne se
perd silencieusement au bord, et deux maillages couvrent exactement le même
domaine. Les cellules découpées portent ``clipped=True``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import h3
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

from amtgo.errors import TopologyError
from amtgo.geo.crs import M2_PER_KM2, area_km2, to_equal_area, to_wgs84
from amtgo.geo.mesh import Cell, FamilyOps, MeshDefinition, MeshFamily

# Approximation du kilomètre par degré, utilisée UNIQUEMENT pour densifier le
# contour de l'emprise lors de la recherche de cellules candidates (le test
# d'intersection qui suit est exact).
_KM_PER_DEGREE = 111.0


def polygonal_part(geom: BaseGeometry) -> Polygon | MultiPolygon | None:
    """Partie surfacique d'un résultat d'intersection (élimine points et lignes de contact)."""
    if geom.is_empty:
        return None
    if isinstance(geom, Polygon | MultiPolygon):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon) and not g.is_empty]
    polys: list[Polygon] = []
    for g in getattr(geom, "geoms", []):
        if isinstance(g, MultiPolygon):
            polys.extend(g.geoms)
    parts.extend(polys)
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)


# --- H3 -----------------------------------------------------------------------


class H3Ops:
    """H3 comme *index analytique hiérarchique* uniquement (prompt §6, 07 §6).

    Imbrication approximative : les 7 enfants d'une cellule H3 ne pavent pas
    exactement son hexagone. Les transferts entre niveaux passent donc par les
    géométries (``multiscale``), jamais par le seul pointeur parent.
    """

    def exact_nesting(self) -> bool:
        return False

    @staticmethod
    def _hexagon(cell_id: str) -> Polygon:
        poly = Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell_id)])
        if not poly.is_valid:
            raise TopologyError(f"cellule H3 {cell_id} invalide")
        return poly

    def candidate_ids(self, definition: MeshDefinition, extent: BaseGeometry) -> set[str]:
        res = definition.resolution
        ids = set(h3.geo_to_cells(extent.__geo_interface__, res))
        # Cellules à cheval sur le contour, dont le centre est hors emprise.
        step_deg = h3.average_hexagon_edge_length(res, unit="km") / _KM_PER_DEGREE / 2.0
        boundary = extent.boundary.segmentize(step_deg)
        for line in getattr(boundary, "geoms", [boundary]):
            for lng, lat in line.coords:
                ids.add(h3.latlng_to_cell(lat, lng, res))
        expanded = set(ids)
        for c in ids:
            expanded.update(h3.grid_disk(c, 1))
        return expanded

    def build_cells(self, definition: MeshDefinition, ids: Iterable[str], extent: BaseGeometry) -> list[Cell]:
        res = definition.resolution
        inside = prep(extent)
        cells = []
        for cid in sorted(set(ids)):
            hexagon = self._hexagon(cid)
            if not inside.intersects(hexagon):
                continue
            parent = h3.cell_to_parent(cid, res - 1) if res > 0 else None
            if inside.contains(hexagon):
                cells.append(Cell(cid, res, hexagon, area_km2(hexagon), parent, False))
                continue
            clipped = polygonal_part(hexagon.intersection(extent))
            if clipped is None:
                continue
            cells.append(Cell(cid, res, clipped, area_km2(clipped), parent, True))
        return cells

    def neighbor_ids(self, definition: MeshDefinition, cell_id: str) -> set[str]:
        return set(h3.grid_disk(cell_id, 1)) - {cell_id}

    def parent_id(self, definition: MeshDefinition, cell_id: str) -> str | None:
        res = h3.get_resolution(cell_id)
        return h3.cell_to_parent(cell_id, res - 1) if res > 0 else None

    def child_ids(self, definition: MeshDefinition, cell_id: str) -> list[str]:
        res = h3.get_resolution(cell_id)
        return sorted(h3.cell_to_children(cell_id, res + 1))


# --- Grille carrée en projection équivalente ------------------------------------

# Densification des arêtes avant reprojection en 4326 : 8 segments par côté.
_GRID_EDGE_SEGMENTS = 8


class GridLaeaOps:
    """Carrés alignés sur l'origine LAEA ; niveau L de côté ``base / 2**L``.

    Imbrication exacte : 4 enfants pavent exactement le parent. Le découpage se
    fait dans l'espace équivalent, où l'aire est exacte.
    """

    def exact_nesting(self) -> bool:
        return True

    @staticmethod
    def side_m(definition: MeshDefinition, level: int) -> float:
        assert definition.grid_base_km is not None
        return definition.grid_base_km * 1000.0 / (2.0**level)

    @staticmethod
    def parse(cell_id: str) -> tuple[int, int, int]:
        try:
            tag, i, j = cell_id.split("_")
            if not tag.startswith("g"):
                raise ValueError
            return int(tag[1:]), int(i), int(j)
        except ValueError as exc:
            raise TopologyError(f"identifiant de grille invalide : {cell_id!r}") from exc

    @staticmethod
    def fmt(level: int, i: int, j: int) -> str:
        return f"g{level}_{i}_{j}"

    def candidate_ids(self, definition: MeshDefinition, extent: BaseGeometry) -> set[str]:
        level = definition.resolution
        s = self.side_m(definition, level)
        minx, miny, maxx, maxy = to_equal_area(extent).bounds
        return {
            self.fmt(level, i, j)
            for i in range(math.floor(minx / s), math.ceil(maxx / s))
            for j in range(math.floor(miny / s), math.ceil(maxy / s))
        }

    def build_cells(self, definition: MeshDefinition, ids: Iterable[str], extent: BaseGeometry) -> list[Cell]:
        projected = to_equal_area(extent)
        inside = prep(projected)
        cells = []
        for cid in sorted(set(ids)):
            level, i, j = self.parse(cid)
            if level != definition.resolution:
                raise TopologyError(f"{cid} n'est pas au niveau {definition.resolution}")
            s = self.side_m(definition, level)
            sq = box(i * s, j * s, (i + 1) * s, (j + 1) * s)
            if not inside.intersects(sq):
                continue
            parent = self.fmt(level - 1, i // 2, j // 2) if level > 0 else None
            if inside.contains(sq):
                geom_ea: BaseGeometry = sq.segmentize(s / _GRID_EDGE_SEGMENTS)
                clipped = False
            else:
                part = polygonal_part(sq.intersection(projected))
                if part is None:
                    continue
                geom_ea, clipped = part.segmentize(s / _GRID_EDGE_SEGMENTS), True
            geom = to_wgs84(geom_ea)
            if not isinstance(geom, Polygon | MultiPolygon) or not geom.is_valid:
                raise TopologyError(f"cellule {cid} invalide après reprojection")
            cells.append(Cell(cid, level, geom, geom_ea.area / M2_PER_KM2, parent, clipped))
        return cells

    def neighbor_ids(self, definition: MeshDefinition, cell_id: str) -> set[str]:
        level, i, j = self.parse(cell_id)
        return {self.fmt(level, i + di, j + dj) for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))}

    def parent_id(self, definition: MeshDefinition, cell_id: str) -> str | None:
        level, i, j = self.parse(cell_id)
        return self.fmt(level - 1, i // 2, j // 2) if level > 0 else None

    def child_ids(self, definition: MeshDefinition, cell_id: str) -> list[str]:
        level, i, j = self.parse(cell_id)
        return sorted(self.fmt(level + 1, 2 * i + di, 2 * j + dj) for di in (0, 1) for dj in (0, 1))


FAMILIES: dict[MeshFamily, FamilyOps] = {
    MeshFamily.H3: H3Ops(),
    MeshFamily.GRID_LAEA: GridLaeaOps(),
}


def ops_for(definition: MeshDefinition) -> FamilyOps:
    return FAMILIES[definition.family]
