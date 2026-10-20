"""Flux de mobilité typés (prompt §25). Toute donnée de mobilité fine est SENSITIVE (03 §20)."""

from __future__ import annotations

from enum import StrEnum

import numpy as np
from pydantic import BaseModel, ConfigDict
from scipy import sparse

from amtgo.core.uncertainty import UncertainValue


class FlowType(StrEnum):
    MIGRATION = "migration"
    COMMUTE = "commute"
    PASTORAL = "pastoral"
    TRADE = "trade"
    FAMILY = "family"
    PILGRIMAGE = "pilgrimage"
    EDUCATION = "education"


class MobilityFlow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: str
    destination: str
    population_concept: str  # concept d'une ontologie (ou "all")
    flow_type: FlowType
    season: str | None
    mean: float
    uncertainty: UncertainValue


def flow_matrix(flows: list[MobilityFlow], cell_ids: list[str], concept: str) -> sparse.csr_matrix:
    """Matrice symétrisée des flux moyens d'un concept, cellule × cellule."""
    pos = {c: k for k, c in enumerate(cell_ids)}
    rows, cols, vals = [], [], []
    for f in flows:
        if f.population_concept not in (concept, "all"):
            continue
        rows.append(pos[f.origin])
        cols.append(pos[f.destination])
        vals.append(f.mean)
    n = len(cell_ids)
    m = sparse.csr_matrix((np.array(vals, dtype=float), (rows, cols)), shape=(n, n))
    return (m + m.T).tocsr() * 0.5
