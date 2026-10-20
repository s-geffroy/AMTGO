"""Partitions évaluées et vecteurs de frontière (02 §8, prompt §85).

Une partition affecte chaque cellule d'un maillage à une juridiction, niveau par
niveau (ex. district ⊂ État). Ce n'est **pas** une proposition : à M5, seules
sont évaluées des partitions déclarées (statu quo, sondes de test) ; la
génération de candidats est M8.

Frontière vectorielle σ_ij = [σ^P, σ^C, σ^E, σ^M, σ^R, σ^S] ∈ [0,1]^6 : la
frontière entre deux cellules est celle du niveau le plus élevé qui les sépare.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.errors import TopologyError


class BorderDim(StrEnum):
    POLITICAL = "P"
    CULTURAL = "C"
    ECONOMIC = "E"
    MOBILITY = "M"
    RESOURCES = "R"
    SECURITY = "S"


class BorderVector(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strength: dict[BorderDim, float]

    @model_validator(mode="after")
    def _complete(self) -> Self:
        missing = set(BorderDim) - set(self.strength)
        if missing:
            raise ValueError(f"vecteur de frontière incomplet : {sorted(d.value for d in missing)}")
        for d, v in self.strength.items():
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"σ^{d.value} hors [0,1]")
        return self

    def get(self, d: BorderDim) -> float:
        return self.strength[d]


@dataclass(frozen=True)
class PartitionLevel:
    name: str
    assignment: np.ndarray  # (N,) indice de juridiction par cellule
    jurisdictions: list[str]
    border: BorderVector  # frontière entre deux juridictions distinctes de ce niveau


@dataclass(frozen=True)
class Partition:
    """Niveaux ordonnés du plus élevé (ex. État) au plus local (ex. district)."""

    mesh_id: str
    cell_ids: list[str]
    levels: list[PartitionLevel]

    def __post_init__(self) -> None:
        n = len(self.cell_ids)
        for lv in self.levels:
            if lv.assignment.shape != (n,):
                raise TopologyError(f"niveau {lv.name} : affectation de taille incorrecte")
            if lv.assignment.min() < 0 or lv.assignment.max() >= len(lv.jurisdictions):
                # Toute cellule a une juridiction : pas d'orphelin (prompt §85).
                raise TopologyError(f"niveau {lv.name} : cellule sans juridiction")
        for upper, lower in zip(self.levels, self.levels[1:], strict=False):
            # Emboîtement : une juridiction locale n'appartient qu'à une juridiction supérieure.
            for j in range(len(lower.jurisdictions)):
                parents = np.unique(upper.assignment[lower.assignment == j])
                if len(parents) > 1:
                    raise TopologyError(f"{lower.jurisdictions[j]} est à cheval sur plusieurs {upper.name}")

    def pair_strength(self, rows: np.ndarray, cols: np.ndarray, dim: BorderDim) -> np.ndarray:
        """σ^{dim} pour des paires de cellules (indices) : niveau le plus élevé qui les sépare."""
        out = np.zeros(len(rows))
        decided = np.zeros(len(rows), dtype=bool)
        for lv in self.levels:
            differ = (lv.assignment[rows] != lv.assignment[cols]) & ~decided
            out[differ] = lv.border.get(dim)
            decided |= differ
        return out


class PartitionSpec(BaseModel):
    """Déclaration d'un niveau : polygones d'une source, ou regroupement d'un niveau inférieur."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    from_source: str | None = None  # source dont les polygones (admin_code) définissent le niveau
    variable_id: str | None = None
    group_of: str | None = None  # niveau inférieur regroupé
    groups: dict[str, tuple[str, ...]] = Field(default_factory=dict)  # juridiction → préfixes d'admin_code
    border: BorderVector

    @model_validator(mode="after")
    def _one_kind(self) -> Self:
        if (self.from_source is None) == (self.group_of is None):
            raise ValueError(f"niveau {self.name} : from_source XOR group_of")
        return self
