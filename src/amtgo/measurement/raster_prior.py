"""Prior de densité lu sur un raster de population (WorldPop), agrégé aux cellules d'un maillage.

Le raster est lu par bandes horizontales : la mémoire reste bornée quel que
soit le pays (un pays entier à 100 m ne tient pas dans le worker). Chaque bande
est sommée par blocs de ``block_pixels`` × ``block_pixels``. Les valeurs
absentes (nodata) comptent pour zéro. Chaque bloc est affecté à la cellule qui
contient son centre, en projection équivalente.

Approximation explicite : un bloc à cheval sur deux cellules va entièrement à
l'une. L'erreur est bornée par la taille du bloc et disparaît dans les totaux.
La masse des blocs hors du maillage est rapportée, jamais redistribuée.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from amtgo.errors import ConfigurationError, StageInterrupted
from amtgo.geo.crs import AFRICA_LAEA, WGS84, _transformer
from amtgo.geo.support import first_hits
from amtgo.measurement.likelihoods import MeshIndex

# Blocs par bande lue : borne mémoire (≈ hauteur × largeur du raster × 8 octets), pas paramètre scientifique.
STRIP_BLOCKS = 16


@dataclass(frozen=True)
class RasterCellTotals:
    totals: np.ndarray  # (N,) personnes par cellule selon le raster
    raster_total: float
    outside: float  # masse des blocs hors maillage
    blocks: int


def cell_totals(path: Path, idx: MeshIndex, block_pixels: int,
                should_stop: Callable[[], bool] = lambda: False) -> RasterCellTotals:
    import rasterio
    from rasterio.windows import Window

    t = _transformer(WGS84, AFRICA_LAEA)
    totals = np.zeros(len(idx))
    raster_total = outside = 0.0
    blocks = 0
    f = block_pixels
    with rasterio.open(path) as src:
        if src.crs is None or src.crs.to_epsg() != 4326:
            raise ConfigurationError(f"{path.name} : raster attendu en EPSG:4326, reçu {src.crs}")
        width, height = src.width, src.height
        nb_cols = -(-width // f)
        strip = f * STRIP_BLOCKS
        for row0 in range(0, height, strip):
            if should_stop():
                raise StageInterrupted(f"prior raster {path.name}")
            rows = min(strip, height - row0)
            data = src.read(1, window=Window(0, row0, width, rows), masked=True).astype(np.float64).filled(0.0)
            if np.any(data < 0):
                raise ConfigurationError(f"{path.name} : valeurs négatives dans un raster de population")
            nb_rows = -(-rows // f)
            padded = np.zeros((nb_rows * f, nb_cols * f))
            padded[:rows, :width] = data
            sums = padded.reshape(nb_rows, f, nb_cols, f).sum(axis=(1, 3))
            keep = sums > 0
            if not keep.any():
                continue
            r_idx, c_idx = np.nonzero(keep)
            # Centre géométrique du bloc (borné au raster pour le dernier bloc incomplet).
            cy = row0 + r_idx * f + np.minimum(f, rows - r_idx * f) / 2.0
            cx = c_idx * f + np.minimum(f, width - c_idx * f) / 2.0
            lon, lat = src.transform @ (cx, cy)
            x, y = t.transform(np.asarray(lon), np.asarray(lat))
            mass = sums[keep]
            hit = first_hits(idx.tree, np.column_stack([x, y]))
            inside = hit >= 0
            np.add.at(totals, hit[inside], mass[inside])
            raster_total += float(mass.sum())
            outside += float(mass[~inside].sum())
            blocks += int(keep.sum())
    return RasterCellTotals(totals, raster_total, outside, blocks)


def prior_density(cells: RasterCellTotals, idx: MeshIndex, floor_per_km2: float) -> np.ndarray:
    """Densité médiane a priori par cellule (hab./km²), planchée."""
    return np.asarray(np.maximum(cells.totals / idx.area, floor_per_km2))


def summary(cells: RasterCellTotals, idx: MeshIndex, floor_per_km2: float) -> dict[str, Any]:
    dens = cells.totals / idx.area
    return {"raster_total": cells.raster_total, "outside_mesh": cells.outside, "blocks": cells.blocks,
            "cells_at_floor": int((dens < floor_per_km2).sum()), "cells": len(idx)}
