"""Énumérations transverses du corpus V1.0-RC1.

Les noms canoniques sont fixés par ADR-0003. Les valeurs courtes (``"D"``,
``"P"``…) suivent le prompt §11 ; le dictionnaire 10 §21 utilise les noms longs,
qui sont les noms des membres.
"""

from __future__ import annotations

from enum import StrEnum


class EvidenceStatus(StrEnum):
    """Statut de preuve d'une valeur (03 §2).

    L'ordre de *force* est DIRECT > PROXY > HISTORICAL > MODEL > UNKNOWN. Une
    agrégation prend le statut le plus faible de ses entrées, et toute
    transformation par un modèle produit au mieux MODEL : rien ne remonte
    silencieusement vers DIRECT (prompt §11).
    """

    DIRECT = "D"
    PROXY = "P"
    MODEL = "M"
    HISTORICAL = "H"
    UNKNOWN = "U"

    @property
    def strength(self) -> int:
        return _EVIDENCE_STRENGTH[self]

    @classmethod
    def combine(cls, statuses: list[EvidenceStatus]) -> EvidenceStatus:
        """Statut d'une valeur agrégée à partir de ``statuses`` : le plus faible."""
        if not statuses:
            return cls.UNKNOWN
        return min(statuses, key=lambda s: s.strength)

    def through_model(self) -> EvidenceStatus:
        """Statut après passage dans un modèle (fusion, interpolation…)."""
        return EvidenceStatus.combine([self, EvidenceStatus.MODEL])


# Ordinal, non numérique au sens scientifique : sert uniquement à ordonner.
_EVIDENCE_STRENGTH = {
    EvidenceStatus.DIRECT: 4,
    EvidenceStatus.PROXY: 3,
    EvidenceStatus.HISTORICAL: 2,
    EvidenceStatus.MODEL: 1,
    EvidenceStatus.UNKNOWN: 0,
}


class PrivacyClass(StrEnum):
    """Classe d'accès (prompt §50, 03 §24). Ordonnée du plus ouvert au plus fermé."""

    PUBLIC = "PUBLIC"
    CONTROLLED = "CONTROLLED"
    SENSITIVE = "SENSITIVE"
    PROHIBITED = "PROHIBITED"

    @property
    def rank(self) -> int:
        return list(PrivacyClass).index(self)

    @classmethod
    def most_restrictive(cls, classes: list[PrivacyClass]) -> PrivacyClass:
        if not classes:
            # Par défaut prudent : l'absence d'information n'est pas PUBLIC.
            return cls.CONTROLLED
        return max(classes, key=lambda c: c.rank)


class DataZone(StrEnum):
    """Zones du data lake (03 §4)."""

    OPEN_CORE = "OPEN_CORE"
    RESTRICTED_LOCAL = "RESTRICTED_LOCAL"
    SENSITIVE = "SENSITIVE"
    DERIVED_EXPORTABLE = "DERIVED_EXPORTABLE"


class SupportType(StrEnum):
    """Support spatial d'une observation (prompt §14)."""

    POINT = "POINT"
    UNCERTAIN_POINT = "UNCERTAIN_POINT"
    POLYGON = "POLYGON"
    RASTER = "RASTER"
    ADMIN = "ADMIN"
    NETWORK = "NETWORK"
    HYPEREDGE = "HYPEREDGE"
    NATIONAL = "NATIONAL"


class RecommendationStatus(StrEnum):
    """Statut de publication (prompt §75, 05 §21)."""

    ROBUST = "ROBUST"
    CONDITIONAL = "CONDITIONAL"
    EXPLORATORY = "EXPLORATORY"
    DATA_LIMITED = "DATA_LIMITED"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"

    @property
    def allows_sharp_border(self) -> bool:
        """Pas de frontière nette pour DATA_LIMITED ni NOT_IDENTIFIABLE."""
        return self not in (RecommendationStatus.DATA_LIMITED, RecommendationStatus.NOT_IDENTIFIABLE)


class ComputabilityClass(StrEnum):
    """Classe de calculabilité d'une zone (prompt §74, 03 §32)."""

    A = "A"  # rich empirical support
    B = "B"  # usable with uncertainty
    C = "C"  # exploratory only
    D = "D"  # insufficient for recommendation

    @property
    def allows_territorial_recommendation(self) -> bool:
        return self is not ComputabilityClass.D


class MapMode(StrEnum):
    """Modes de carte (prompt §77). C_DEEP reste non implémenté."""

    R = "R"
    C_SHALLOW = "C_SHALLOW"
    C_DEEP = "C_DEEP"
