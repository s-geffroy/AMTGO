"""Observations (prompt §13-14, schéma 10 §2).

Une observation est ce qu'une source dit, à un support spatial et une période
donnés, avec sa qualité et son statut de preuve. Elle ne dit rien de « la vraie
structure » : c'est le rôle des modèles de mesure (M3).

Temporalité : ``valid_from`` / ``valid_until`` (temps de validité) et
``recorded_at`` (temps d'enregistrement) sont distincts et jamais mélangés.
Support : un point géomasqué est une *distribution* (``displacement_km``), pas
un point exact (03 §6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field
from shapely import wkt as shapely_wkt
from shapely.geometry.base import BaseGeometry

from amtgo.core.entity import Entity
from amtgo.core.enums import EvidenceStatus, PrivacyClass, SupportType
from amtgo.core.quality import QualityVector
from amtgo.core.uncertainty import UncertainValue
from amtgo.errors import TopologyError
from amtgo.utils.canonical import stable_uuid

_GEOMETRY_SUPPORTS = {
    SupportType.POINT,
    SupportType.UNCERTAIN_POINT,
    SupportType.POLYGON,
    SupportType.ADMIN,
    SupportType.NETWORK,
}


class Observation(Entity):
    source_id: str  # UUID de la Source (str pour la sérialisation parquet)
    variable_id: str
    ontology_id: str | None = None
    support_type: SupportType
    geometry_wkt: str | None = None
    raster_ref: str | None = None
    admin_code: str | None = None
    displacement_km: float | None = Field(default=None, gt=0.0)
    valid_from: datetime
    valid_until: datetime | None = None
    recorded_at: datetime
    value: UncertainValue | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    quality: QualityVector
    evidence_status: EvidenceStatus
    sensitivity: PrivacyClass

    def check(self) -> None:
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until antérieur à valid_from")
        st = self.support_type
        if st in _GEOMETRY_SUPPORTS and not self.geometry_wkt:
            raise ValueError(f"support {st.value} sans géométrie")
        if st is SupportType.UNCERTAIN_POINT and self.displacement_km is None:
            raise ValueError("UNCERTAIN_POINT exige un modèle de déplacement (displacement_km)")
        if st is SupportType.POINT and self.displacement_km is not None:
            raise ValueError("un point géomasqué doit être déclaré UNCERTAIN_POINT")
        if st is SupportType.RASTER and not self.raster_ref:
            raise ValueError("support RASTER sans raster_ref")
        if st is SupportType.NATIONAL and not self.admin_code:
            raise ValueError("support NATIONAL sans admin_code")
        if self.geometry_wkt:
            geom = self.geometry()
            if geom is None or geom.is_empty or not geom.is_valid:
                raise TopologyError(f"géométrie invalide pour {self.variable_id}")

    def geometry(self) -> BaseGeometry | None:
        return shapely_wkt.loads(self.geometry_wkt) if self.geometry_wkt else None

    @staticmethod
    def make_id(source_id: str, variable_id: str, key: str, valid_from: datetime) -> str:
        """Identifiant stable : même source, variable, clé et période → même id."""
        return str(stable_uuid("observation", {
            "source": source_id, "variable": variable_id, "key": key,
            "valid_from": valid_from.isoformat(),
        }))
