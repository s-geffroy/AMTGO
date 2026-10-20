"""Sources synthétiques déterministes issues d'un même monde à vérité connue.

``instrument: survey`` produit des comptes de zones d'énumération géomasquées
(UNCERTAIN_POINT) ; ``instrument: census`` produit des totaux de districts
(ADMIN). Aucune catégorie identitaire avant M4/M5. La vérité du monde n'est
jamais écrite dans les observations : seuls les instruments le sont.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

from amtgo.core.enums import SupportType
from amtgo.core.uncertainty import DistributionType, UncertainValue
from amtgo.data.observations import Observation
from amtgo.data.sources import ResourceRef, SourceManifest
from amtgo.data.synthetic_world import (
    CensusDesign,
    SurveyDesign,
    SyntheticWorld,
    simulate_census,
    simulate_survey,
)
from amtgo.errors import ConfigurationError
from amtgo.utils.canonical import canonical_json, content_hash

VARIABLE_EA_COUNT = "population_count_ea"
VARIABLE_DISTRICT_TOTAL = "population_total_admin"


def world_of(manifest: SourceManifest) -> SyntheticWorld:
    p = manifest.retrieval.parameters
    if "world" not in p:
        raise ConfigurationError(f"{manifest.source_id} : bloc 'world' manquant")
    return SyntheticWorld.from_params(p["world"])


class SyntheticAdapter:
    def discover(self, manifest: SourceManifest) -> list[ResourceRef]:
        return [ResourceRef(name="synthetic")]

    def fetch(self, manifest: SourceManifest, ref: ResourceRef, cache_dir: Path) -> Path:
        # Rien à télécharger : le « fichier » est le jeu de paramètres, figé dans le manifeste.
        target = cache_dir / manifest.source_id / manifest.release / "parameters.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(canonical_json(manifest.retrieval.parameters), encoding="utf-8")
        return target

    def validate(self, manifest: SourceManifest, ref: ResourceRef, path: Path) -> str:
        return content_hash(manifest.retrieval.parameters)

    def normalize(
        self, manifest: SourceManifest, files: dict[str, Path], recorded_at: datetime
    ) -> Iterator[Observation]:
        p: dict[str, Any] = manifest.retrieval.parameters
        if manifest.temporal_start is None:
            raise ConfigurationError("synthetic : temporal_start requis")
        world = world_of(manifest)
        valid_from = datetime.combine(manifest.temporal_start, time.min, tzinfo=UTC)
        valid_until = (datetime.combine(manifest.temporal_end, time.max, tzinfo=UTC)
                       if manifest.temporal_end else None)
        src = str(manifest.source_uuid)
        instrument = p.get("instrument")
        common: dict[str, Any] = dict(
            version=manifest.release, source_id=src, valid_from=valid_from, valid_until=valid_until,
            recorded_at=recorded_at, quality=manifest.quality,
            evidence_status=manifest.default_evidence_status, sensitivity=manifest.privacy_class,
        )

        if instrument == "survey":
            design = SurveyDesign.from_params(p.get("survey", {}))
            for ea in simulate_survey(world, design):
                lon, lat = ea.released_lonlat
                yield Observation(
                    id=Observation.make_id(src, VARIABLE_EA_COUNT, ea.key, valid_from),
                    variable_id=VARIABLE_EA_COUNT, support_type=SupportType.UNCERTAIN_POINT,
                    geometry_wkt=f"POINT ({lon:.6f} {lat:.6f})",
                    displacement_km=design.displacement_km,
                    value=UncertainValue.exact(float(ea.count)),
                    attributes={"synthetic": True, "world_hash": world.world_hash,
                                "ea_area_km2": design.ea_area_km2},
                    **common,
                )
        elif instrument == "census":
            design_c = CensusDesign.from_params(p.get("census", {}))
            for d in simulate_census(world, design_c):
                yield Observation(
                    id=Observation.make_id(src, VARIABLE_DISTRICT_TOTAL, d.key, valid_from),
                    variable_id=VARIABLE_DISTRICT_TOTAL, support_type=SupportType.ADMIN,
                    geometry_wkt=d.polygon.wkt, admin_code=d.key,
                    value=UncertainValue(mean=d.reported_total, std=d.reported_sd,
                                         distribution_type=DistributionType.NORMAL),
                    attributes={"synthetic": True, "world_hash": world.world_hash},
                    **common,
                )
        else:
            raise ConfigurationError(f"synthetic : instrument inconnu {instrument!r} (survey | census)")
