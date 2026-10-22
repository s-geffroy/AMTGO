"""Adapters de sources. Seul endroit où le réseau peut être touché (prompt §67)."""

from __future__ import annotations

from amtgo.data.adapters.admin import AdminBoundariesAdapter, AdminTableAdapter
from amtgo.data.adapters.base import SourceAdapter
from amtgo.data.adapters.natural_earth import NaturalEarthAdapter
from amtgo.data.adapters.synthetic import SyntheticAdapter
from amtgo.data.adapters.worldpop import WorldPopAdapter
from amtgo.errors import ConfigurationError

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "admin_boundaries": AdminBoundariesAdapter,
    "admin_table": AdminTableAdapter,
    "natural_earth": NaturalEarthAdapter,
    "synthetic": SyntheticAdapter,
    "worldpop": WorldPopAdapter,
}


def get_adapter(name: str) -> SourceAdapter:
    try:
        return ADAPTERS[name]()
    except KeyError as exc:
        raise ConfigurationError(f"adapter inconnu : {name!r}") from exc


__all__ = ["ADAPTERS", "SourceAdapter", "get_adapter"]
