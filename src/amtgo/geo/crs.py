"""Systèmes de référence (prompt §64, ADR-0008).

Stockage en EPSG:4326. Toute surface ou distance passe par une projection
équivalente : Lambert azimutale équivalente centrée sur l'Afrique. Aucun calcul
métrique en degrés.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry.base import BaseGeometry

WGS84 = "EPSG:4326"
# Centre approximatif du continent ; équivalente partout, déformation angulaire
# croissante loin du centre (sans effet sur les surfaces).
AFRICA_LAEA = "+proj=laea +lat_0=5 +lon_0=20 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs"

M2_PER_KM2 = 1_000_000.0

# Les géométries stockées ont des arêtes droites en lon/lat. Avant projection,
# on les densifie pour que leur image équivalente suive ces arêtes (courbes en
# LAEA) : ~5 km de pas, erreur de flèche < 1 m. Fidélité géométrique, pas
# paramètre scientifique.
DENSIFY_DEG = 0.05


@lru_cache(maxsize=4)
def _transformer(src: str, dst: str) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def _reproject(geom: BaseGeometry, src: str, dst: str) -> BaseGeometry:
    t = _transformer(src, dst)

    def fn(coords: np.ndarray) -> np.ndarray:
        x, y = t.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(geom, fn)


def to_equal_area(geom: BaseGeometry) -> BaseGeometry:
    return _reproject(geom.segmentize(DENSIFY_DEG), WGS84, AFRICA_LAEA)


def to_wgs84(geom: BaseGeometry) -> BaseGeometry:
    return _reproject(geom, AFRICA_LAEA, WGS84)


def area_km2(geom_wgs84: BaseGeometry) -> float:
    return float(to_equal_area(geom_wgs84).area / M2_PER_KM2)
