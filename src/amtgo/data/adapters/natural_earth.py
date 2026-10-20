"""Natural Earth admin-0 (domaine public) : fond de carte des pays actuels (ADR-0011).

Natural Earth représente des frontières *de facto*, selon sa propre politique
éditoriale ; ce n'est ni une source juridique ni une prise de position. Les
observations sont donc de statut PROXY pour le concept « frontière juridique ».
Les lignes disputées / indéfinies sont conservées comme telles et rendues en
pointillé.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

from shapely.geometry import box, shape
from shapely.validation import make_valid

from amtgo.core.enums import SupportType
from amtgo.data.adapters.files import PinnedFileMixin
from amtgo.data.observations import Observation
from amtgo.data.sources import SourceManifest
from amtgo.errors import ConfigurationError

# Attributs conservés : descriptifs uniquement (pas de PIB ni de population,
# hors du rôle autorisé de cette source).
_KEEP = ("ADM0_A3", "NAME", "NAME_FR", "TYPE", "SOVEREIGNT", "NOTE_ADM0", "NOTE_BRK")


class NaturalEarthAdapter(PinnedFileMixin):
    def normalize(
        self, manifest: SourceManifest, files: dict[str, Path], recorded_at: datetime
    ) -> Iterator[Observation]:
        params = manifest.retrieval.parameters
        continent = params.get("continent")
        bbox = params.get("bbox")
        if not continent or not bbox:
            raise ConfigurationError("natural_earth : paramètres 'continent' et 'bbox' requis")
        area = box(*bbox)
        if manifest.temporal_start is None:
            raise ConfigurationError("natural_earth : temporal_start requis (temps de validité)")
        valid_from = datetime.combine(manifest.temporal_start, time.min, tzinfo=UTC)
        src = str(manifest.source_uuid)
        layers: dict[str, str] = params.get("layers", {})

        for resource_name, path in sorted(files.items()):
            variable = layers.get(resource_name)
            if variable is None:
                raise ConfigurationError(f"natural_earth : variable non déclarée pour {resource_name}")
            features = json.loads(path.read_text(encoding="utf-8"))["features"]
            for feat in features:
                props: dict[str, Any] = feat.get("properties") or {}
                geom = shape(feat["geometry"])
                if variable == "admin0_polygon":
                    if props.get("CONTINENT") != continent:
                        continue
                elif not geom.intersects(area):
                    continue
                if not geom.is_valid:
                    geom = make_valid(geom)
                key = str(props.get("ADM0_A3") or props.get("BRK_A3") or props.get("NE_ID"))
                attrs = {k.lower(): props[k] for k in _KEEP if props.get(k) not in (None, "")}
                support = SupportType.ADMIN
                if variable == "admin0_boundary_line":
                    key = str(props.get("NE_ID"))
                    attrs = {"featurecla": props.get("FEATURECLA"), "name": props.get("NAME")}
                    support = SupportType.NETWORK
                yield Observation(
                    id=Observation.make_id(src, variable, key, valid_from),
                    version=manifest.release,
                    source_id=src,
                    variable_id=variable,
                    support_type=support,
                    geometry_wkt=geom.wkt,
                    admin_code=key if support is SupportType.ADMIN else None,
                    valid_from=valid_from,
                    recorded_at=recorded_at,
                    attributes=attrs,
                    quality=manifest.quality,
                    evidence_status=manifest.default_evidence_status,
                    sensitivity=manifest.privacy_class,
                )
