"""Source synthétique déterministe (M1 ; mondes A–F en M5).

Le territoire synthétique est placé **en plein océan** (Atlantique Sud, au large
de toute côte) : aucune lecture ne peut le confondre avec une population réelle.
Il ne contient à ce stade que des comptes de population géomasqués — aucune
catégorie identitaire avant M4/M5.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, box
from shapely.prepared import prep

from amtgo.core.enums import SupportType
from amtgo.core.uncertainty import UncertainValue
from amtgo.data.observations import Observation
from amtgo.data.sources import ResourceRef, SourceManifest
from amtgo.errors import ConfigurationError
from amtgo.geo.crs import AFRICA_LAEA, WGS84, to_equal_area
from amtgo.utils.canonical import content_hash


def _param[T](params: dict[str, Any], name: str, kind: type[T]) -> T:
    if name not in params:
        raise ConfigurationError(f"synthetic : paramètre {name!r} manquant")
    try:
        return kind(params[name])  # type: ignore[call-arg]
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"synthetic : paramètre {name!r} invalide ({exc})") from exc


class SyntheticAdapter:
    def discover(self, manifest: SourceManifest) -> list[ResourceRef]:
        return [ResourceRef(name="synthetic")]

    def fetch(self, manifest: SourceManifest, ref: ResourceRef, cache_dir: Path) -> Path:
        # Rien à télécharger : le « fichier » est le jeu de paramètres, figé dans le manifeste.
        target = cache_dir / manifest.source_id / manifest.release / "parameters.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        from amtgo.utils.canonical import canonical_json

        target.write_text(canonical_json(manifest.retrieval.parameters), encoding="utf-8")
        return target

    def validate(self, manifest: SourceManifest, ref: ResourceRef, path: Path) -> str:
        return content_hash(manifest.retrieval.parameters)

    def normalize(
        self, manifest: SourceManifest, files: dict[str, Path], recorded_at: datetime
    ) -> Iterator[Observation]:
        p: dict[str, Any] = manifest.retrieval.parameters
        seed = _param(p, "seed", int)
        bbox = _param(p, "bbox", list)
        try:
            minx, miny, maxx, maxy = (float(v) for v in bbox)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"synthetic : paramètre 'bbox' invalide ({exc})") from exc
        n_clusters = _param(p, "n_clusters", int)
        displacement_km = _param(p, "displacement_km", float)
        pop_mean = _param(p, "population_mean", float)
        pop_dispersion = _param(p, "population_dispersion", float)
        n_samples = _param(p, "n_samples", int)
        if manifest.temporal_start is None:
            raise ConfigurationError("synthetic : temporal_start requis")

        rng = np.random.default_rng(seed)
        valid_from = datetime.combine(manifest.temporal_start, time.min, tzinfo=UTC)
        src = str(manifest.source_uuid)
        to_wgs = Transformer.from_crs(AFRICA_LAEA, WGS84, always_xy=True)
        # Densité uniforme EN SURFACE dans l'emprise lon/lat : tirage avec rejet dans
        # l'emprise projetée (loin du centre LAEA, elle n'est pas un rectangle).
        region = to_equal_area(box(minx, miny, maxx, maxy).segmentize(0.05))
        inside = prep(region)
        bx0, by0, bx1, by1 = region.bounds
        xs: list[float] = []
        ys: list[float] = []
        while len(xs) < n_clusters:
            x, y = rng.uniform(bx0, bx1), rng.uniform(by0, by1)
            if inside.contains(Point(x, y)):
                xs.append(float(x))
                ys.append(float(y))
        for k in range(n_clusters):
            lon, lat = to_wgs.transform(xs[k], ys[k])
            # Gamma-Poisson : la dispersion encode une incertitude de comptage.
            shape_k = pop_dispersion
            rate = shape_k / pop_mean
            lam = rng.gamma(shape_k, 1.0 / rate, n_samples)
            draws = rng.poisson(lam).astype(float)
            yield Observation(
                id=Observation.make_id(src, "population_count", f"cluster-{k:05d}", valid_from),
                version=manifest.release,
                source_id=src,
                variable_id="population_count",
                support_type=SupportType.UNCERTAIN_POINT,
                geometry_wkt=f"POINT ({lon:.6f} {lat:.6f})",
                displacement_km=displacement_km,
                valid_from=valid_from,
                recorded_at=recorded_at,
                value=UncertainValue.from_samples(draws),
                attributes={"synthetic": True, "cluster": k},
                quality=manifest.quality,
                evidence_status=manifest.default_evidence_status,
                sensitivity=manifest.privacy_class,
            )
