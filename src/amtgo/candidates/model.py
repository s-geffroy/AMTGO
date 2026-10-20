"""Candidats territoriaux : familles, manifeste du générateur, enregistrement (prompt §38, §78, 07 §11).

Un candidat est une **unité analytique**, jamais une proposition (09 §15). Il
n'est pas évalué ici : M8 génère et vérifie (invariants §85, stabilité
multi-échelle), l'optimiseur (M10) compare.

Le générateur ne doit pas imposer la réponse :

- les baselines STATUS_QUO, NO_TERRITORIAL_CHANGE et INSTITUTIONAL_ONLY_REFORM
  sont **toujours** présentes (prompt §78) ;
- plusieurs familles, chacune avec plusieurs paramètres, et un balayage du
  nombre d'États (sortie, jamais une pénalité, prompt §42) ;
- les familles territoriales n'utilisent que la population et la géographie, et
  jamais les parts de groupes. Une famille dont les données manquent est
  déclarée NOT_AVAILABLE, jamais remplacée par une autre.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.utils.canonical import content_hash


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CandidateFamily(StrEnum):
    STATUS_QUO = "STATUS_QUO"
    NO_TERRITORIAL_CHANGE = "NO_TERRITORIAL_CHANGE"
    INSTITUTIONAL_ONLY_REFORM = "INSTITUTIONAL_ONLY_REFORM"
    GEOGRAPHIC = "GEOGRAPHIC"  # k-means pondéré par la population, multi-départ
    GEOGRAPHIC_SEEDED = "GEOGRAPHIC_SEEDED"  # k-means amorcé sur le statu quo (graines géographiques)
    GRAPH_SPECTRAL = "GRAPH_SPECTRAL"  # coupe normalisée du graphe des liens
    GRAPH_COMMUNITY = "GRAPH_COMMUNITY"  # communautés (Louvain) du graphe d'adjacence pondéré
    HISTORICAL = "HISTORICAL"  # frontières administratives historiques (rôle dédié)
    LANGUAGE = "LANGUAGE"
    MOBILITY = "MOBILITY"

    @property
    def is_baseline(self) -> bool:
        return self in BASELINES


BASELINES = (CandidateFamily.STATUS_QUO, CandidateFamily.NO_TERRITORIAL_CHANGE,
             CandidateFamily.INSTITUTIONAL_ONLY_REFORM)

# Ce que chaque baseline laisse varier (M9 compose les institutions à géométrie fixe).
BASELINE_SCOPE = {
    CandidateFamily.STATUS_QUO: "géométrie et institutions déclarées, inchangées",
    CandidateFamily.NO_TERRITORIAL_CHANGE: "géométrie inchangée ; seule l'application des droits peut varier",
    CandidateFamily.INSTITUTIONAL_ONLY_REFORM: "géométrie inchangée ; compétences, représentation, overlays recomposés",
}

# Rôle qu'une source doit déclarer pour amorcer la famille historique : une carte
# ethnographique (rôle ontology_validation) ne peut donc jamais servir de graine.
ROLE_HISTORICAL_SEED = "historical_boundary_seed"


class CandidateManifest(_Strict):
    generator_id: str
    version: str
    description: str
    level: str  # niveau généré (juridictions souveraines)
    reference_mesh: str  # grille de référence de la distance entre partitions (S^scale)
    state_counts: tuple[int, ...] = Field(min_length=1)  # balayage ; 1 = union, autorisée
    restarts: int = Field(ge=1, le=100)
    community_resolutions: tuple[float, ...] = Field(min_length=1)
    network_kernel_length_km: float = Field(gt=0)
    network_kernel_cutoff: float = Field(gt=1)

    @model_validator(mode="after")
    def _counts(self) -> Self:
        if any(k < 1 for k in self.state_counts) or len(set(self.state_counts)) != len(self.state_counts):
            raise ValueError("state_counts : entiers ≥ 1, sans doublon")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)


@dataclass(frozen=True)
class TerritoryCandidate:
    """Partition candidate d'un maillage au niveau ``level`` (schéma 10 §7)."""

    candidate_id: str
    family: CandidateFamily
    method: str
    params: dict[str, Any]
    mesh_id: str
    level: str
    n_states: int
    assignment_hash: str
    contiguous: bool
    repaired_cells: int  # cellules réaffectées pour rétablir la contiguïté
    population_shares: list[float]
    duplicate_of: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def match_key(self) -> str:
        """Clé d'appariement entre maillages : même famille, mêmes paramètres."""
        return f"{self.family.value}|{content_hash(self.params)}"

    def to_json(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "family": self.family.value, "method": self.method,
                "params": self.params, "mesh_id": self.mesh_id, "level": self.level, "n_states": self.n_states,
                "assignment_hash": self.assignment_hash, "contiguous": self.contiguous,
                "repaired_cells": self.repaired_cells, "population_shares": self.population_shares,
                "duplicate_of": self.duplicate_of, "baseline": self.family.is_baseline,
                "scope": BASELINE_SCOPE.get(self.family), "notes": self.notes}
