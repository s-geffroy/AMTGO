"""WorldPop (population maillée à 100 m, CC BY 4.0) : un *prior*, jamais une observation (03 §5).

WorldPop est un produit modélisé : sa répartition dasymétrique s'appuie sur des
covariables, et ses totaux sont ajustés aux estimations des Nations unies.
L'adapter ne produit donc **qu'une** observation, de support RASTER et de statut
M, qui référence le fichier épinglé (``raster_ref``) et en résume les
métadonnées. La lecture cellule par cellule se fait à l'étape ``raster_prior``,
par bandes. Aucune identité n'est jamais inférée du raster.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, time
from pathlib import Path

import numpy as np
from shapely.geometry import box

from amtgo.core.enums import SupportType
from amtgo.data.adapters.files import PinnedFileMixin
from amtgo.data.observations import Observation
from amtgo.data.sources import SourceManifest
from amtgo.errors import ConfigurationError

# Rangées lues à la fois pour le total de contrôle : borne mémoire, pas paramètre scientifique.
_STRIP_ROWS = 512


def raster_ref(name: str, sha256: str) -> str:
    sha = sha256 if sha256.startswith("sha256:") else "sha256:" + sha256
    return f"{name}@{sha}"


class WorldPopAdapter(PinnedFileMixin):
    def normalize(
        self, manifest: SourceManifest, files: dict[str, Path], recorded_at: datetime
    ) -> Iterator[Observation]:
        import rasterio
        from rasterio.windows import Window

        p = manifest.retrieval.parameters
        variable = p.get("variable")
        if not variable or manifest.temporal_start is None:
            raise ConfigurationError(f"{manifest.source_id} : paramètre 'variable' et temporal_start requis")
        valid_from = datetime.combine(manifest.temporal_start, time.min, tzinfo=UTC)
        valid_until = (datetime.combine(manifest.temporal_end, time.max, tzinfo=UTC)
                       if manifest.temporal_end else None)
        shas = {r.name: r.sha256 or "" for r in manifest.retrieval.resources}
        src_id = str(manifest.source_uuid)
        for name, path in sorted(files.items()):
            with rasterio.open(path) as src:
                if src.crs is None or src.crs.to_epsg() != 4326:
                    raise ConfigurationError(f"{name} : raster attendu en EPSG:4326, reçu {src.crs}")
                total = 0.0
                for row0 in range(0, src.height, _STRIP_ROWS):
                    w = Window(0, row0, src.width, min(_STRIP_ROWS, src.height - row0))
                    total += float(np.sum(src.read(1, window=w, masked=True).astype(np.float64).filled(0.0)))
                b = src.bounds
                attrs = {"width": src.width, "height": src.height, "res_deg": list(src.res),
                         "nodata": src.nodata, "units": "personnes par pixel", "raster_total": total}
            yield Observation(
                id=Observation.make_id(src_id, variable, name, valid_from),
                version=manifest.release, source_id=src_id, variable_id=variable,
                support_type=SupportType.RASTER, raster_ref=raster_ref(name, shas[name]),
                geometry_wkt=box(b.left, b.bottom, b.right, b.top).wkt,
                valid_from=valid_from, valid_until=valid_until, recorded_at=recorded_at,
                attributes=attrs, quality=manifest.quality,
                evidence_status=manifest.default_evidence_status, sensitivity=manifest.privacy_class,
            )
