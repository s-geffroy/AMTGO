"""Sources synthétiques déterministes issues d'un même monde à vérité connue.

``instrument: survey`` produit des comptes de zones d'énumération géomasquées
(UNCERTAIN_POINT) ; ``instrument: census`` produit des totaux de districts
(ADMIN) ; ``instrument: fiscal`` des comptes de districts (M6) ;
``instrument: policy_panel`` un panel de districts × années (M7). Aucune catégorie
identitaire avant M4/M5. La vérité du monde n'est jamais écrite dans les
observations : seuls les instruments le sont.
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
    FiscalDesign,
    PanelDesign,
    SurveyDesign,
    SyntheticWorld,
    group_layer,
    simulate_census,
    simulate_fiscal,
    simulate_historical_map,
    simulate_identity_counts,
    simulate_panel,
    simulate_survey,
)
from amtgo.errors import ConfigurationError
from amtgo.utils.canonical import canonical_json, content_hash

VARIABLE_EA_COUNT = "population_count_ea"
VARIABLE_DISTRICT_TOTAL = "population_total_admin"
VARIABLE_IDENTITY_COUNTS = "identity_self_counts"
VARIABLE_HISTORICAL_LABEL = "identity_historical_label"
VARIABLE_FISCAL_REVENUE = "fiscal_revenue_admin"
VARIABLE_SERVICE_COST = "service_cost_admin"
VARIABLE_PANEL_OUTCOME = "policy_panel_outcome"
VARIABLE_PANEL_NEGATIVE_CONTROL = "policy_panel_negative_control"


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
            eas = simulate_survey(world, design)
            yield from self._identity(manifest, world, eas, common, valid_from)
            for ea in eas:
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
        elif instrument == "historical_map":
            layer = group_layer(p["world"])
            hp = p.get("historical_map", {})
            if layer is None or "lumping" not in hp:
                raise ConfigurationError("historical_map : couche 'groups' et 'lumping' requis")
            blocks = simulate_historical_map(world, layer, int(hp.get("blocks_x", 3)),
                                             int(hp.get("blocks_y", 3)), dict(hp["lumping"]))
            for b in blocks:
                yield Observation(
                    id=Observation.make_id(src, VARIABLE_HISTORICAL_LABEL, b.key, valid_from),
                    variable_id=VARIABLE_HISTORICAL_LABEL, support_type=SupportType.POLYGON,
                    ontology_id=str(hp["ontology_id"]), geometry_wkt=b.polygon.wkt,
                    attributes={"synthetic": True, "world_hash": world.world_hash, "label": b.label},
                    **common,
                )
        elif instrument == "fiscal":
            design_f = FiscalDesign.from_params(p.get("fiscal", {}))
            for fd in simulate_fiscal(world, design_f):
                for var, mean, sd in ((VARIABLE_FISCAL_REVENUE, fd.revenue, fd.revenue_sd),
                                      (VARIABLE_SERVICE_COST, fd.service_cost, fd.service_cost_sd)):
                    yield Observation(
                        id=Observation.make_id(src, var, fd.key, valid_from),
                        variable_id=var, support_type=SupportType.ADMIN,
                        geometry_wkt=fd.polygon.wkt, admin_code=fd.key,
                        value=UncertainValue(mean=mean, std=sd, distribution_type=DistributionType.NORMAL),
                        attributes={"synthetic": True, "world_hash": world.world_hash},
                        **common,
                    )
        elif instrument == "policy_panel":
            design_p = PanelDesign.from_params(p.get("panel", {}))
            for pd_ in simulate_panel(world, design_p):
                for t, (y, z) in zip(design_p.years, zip(pd_.outcome, pd_.negative_control, strict=True),
                                     strict=True):
                    start = datetime(int(t), 1, 1, tzinfo=UTC)
                    end = datetime(int(t), 12, 31, 23, 59, 59, tzinfo=UTC)
                    for var, v in ((VARIABLE_PANEL_OUTCOME, y), (VARIABLE_PANEL_NEGATIVE_CONTROL, z)):
                        yield Observation(
                            id=Observation.make_id(src, var, pd_.key, start),
                            variable_id=var, support_type=SupportType.ADMIN,
                            geometry_wkt=pd_.polygon.wkt, admin_code=pd_.key,
                            value=UncertainValue.exact(v),
                            attributes={"synthetic": True, "world_hash": world.world_hash,
                                        "treatment_cohort": pd_.cohort, "density": pd_.density},
                            **{**common, "valid_from": start, "valid_until": end},
                        )
        else:
            raise ConfigurationError(f"synthetic : instrument inconnu {instrument!r} "
                                     "(survey | census | historical_map | fiscal | policy_panel)")

    def _identity(self, manifest: SourceManifest, world: SyntheticWorld, eas: list[Any],
                  common: dict[str, Any], valid_from: datetime) -> Iterator[Observation]:
        """Réponses d'auto-identification par EA, si le manifeste en déclare (M4)."""
        p = manifest.retrieval.parameters
        ident = p.get("survey", {}).get("identity")
        layer = group_layer(p["world"])
        if not ident or layer is None:
            return
        respondents = int(ident["respondents"])
        counts = simulate_identity_counts(world, layer, eas, respondents)
        src = str(manifest.source_uuid)
        displacement = float(p["survey"]["displacement_km"])
        for ea, c in zip(eas, counts, strict=True):
            lon, lat = ea.released_lonlat
            yield Observation(
                id=Observation.make_id(src, VARIABLE_IDENTITY_COUNTS, ea.key, valid_from),
                variable_id=VARIABLE_IDENTITY_COUNTS, support_type=SupportType.UNCERTAIN_POINT,
                ontology_id=str(ident["ontology_id"]), geometry_wkt=f"POINT ({lon:.6f} {lat:.6f})",
                displacement_km=displacement, value=UncertainValue.exact(float(respondents)),
                # Poids de plan : population représentée par l'EA (EA tirées uniformément en surface).
                attributes={"synthetic": True, "world_hash": world.world_hash, "counts": c,
                            "design_weight": float(max(ea.count, 0))},
                **common,
            )
