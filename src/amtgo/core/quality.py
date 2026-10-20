"""Qualité multidimensionnelle (prompt §12, 03 §3).

Il n'existe volontairement aucun ``quality_score: float`` : les dimensions ne
sont pas commensurables, et les agréger cacherait un choix normatif. Les
opérations fournies restent dimension par dimension.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_Unit = Field(ge=0.0, le=1.0)


class QualityVector(BaseModel):
    """Vecteur de qualité Q_o d'une observation ou d'une source, chaque dimension dans [0,1]."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_reliability: float = _Unit
    spatial_precision: float = _Unit
    temporal_precision: float = _Unit
    construct_validity: float = _Unit
    representativeness: float = _Unit
    license_usability: float = _Unit
    privacy_usability: float = _Unit

    def __float__(self) -> float:  # pragma: no cover - garde-fou explicite
        raise TypeError("QualityVector n'a pas de score scalaire (prompt §12)")

    def dimensions(self) -> dict[str, float]:
        return self.model_dump()

    def elementwise_min(self, other: QualityVector) -> QualityVector:
        """Qualité d'un produit dérivé de deux entrées : la plus faible, dimension par dimension."""
        a, b = self.dimensions(), other.dimensions()
        return QualityVector(**{k: min(a[k], b[k]) for k in a})
