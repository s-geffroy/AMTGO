"""Canaux de cohésion, de fragmentation et d'intégration, et leur dimension de frontière d(c).

Table versionnée (ADR-0004), paramètre de modèle enregistré dans chaque run :
aucune correspondance canal → σ n'est implicite.
"""

from __future__ import annotations

from enum import StrEnum

from amtgo.geo.partition import BorderDim


class FragChannel(StrEnum):
    """Canaux de fragmentation (prompt §23)."""

    TERRITORIAL = "territorial"
    NETWORK = "network"
    MOBILITY = "mobility"
    CULTURAL = "cultural"
    INSTITUTIONAL = "institutional"


class IntegChannel(StrEnum):
    """Canaux du tenseur d'intégration (prompt §24)."""

    SPATIAL = "spatial"
    LINGUISTIC = "linguistic"
    FAMILY = "family"
    SOCIAL = "social"
    ECONOMIC = "economic"
    CIVIC = "civic"
    IDENTITY = "identity"


CHANNEL_MAP_VERSION = "1"

FRAG_BORDER: dict[FragChannel, BorderDim] = {
    FragChannel.TERRITORIAL: BorderDim.POLITICAL,
    FragChannel.NETWORK: BorderDim.MOBILITY,
    FragChannel.MOBILITY: BorderDim.MOBILITY,
    FragChannel.CULTURAL: BorderDim.CULTURAL,
    FragChannel.INSTITUTIONAL: BorderDim.POLITICAL,
}

INTEG_BORDER: dict[IntegChannel, BorderDim] = {
    IntegChannel.SPATIAL: BorderDim.MOBILITY,
    IntegChannel.LINGUISTIC: BorderDim.CULTURAL,
    IntegChannel.FAMILY: BorderDim.MOBILITY,
    IntegChannel.SOCIAL: BorderDim.MOBILITY,
    IntegChannel.ECONOMIC: BorderDim.ECONOMIC,
    IntegChannel.CIVIC: BorderDim.POLITICAL,
    IntegChannel.IDENTITY: BorderDim.CULTURAL,
}
