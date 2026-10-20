"""OptimizerManifest : paramètres de l'optimiseur régional (M10), figés dans le RunManifest."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.optimization.objectives import OBJECTIVES, UNKNOWN_OBJECTIVES
from amtgo.utils.canonical import content_hash


class OptimizerManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    optimizer_id: str
    version: str
    description: str
    # Résolution de l'ε-dominance par objectif : un écart plus petit ne départage jamais (ADR-0009).
    epsilon: dict[str, float]
    border_cost_per_km: float = Field(ge=0)  # gestion des frontières, unités du jeu fiscal (PROVISOIRE)
    benchmark_tolerance: float = Field(gt=0, lt=1)  # écart relatif admis au benchmark exact (Gate O)

    @model_validator(mode="after")
    def _objectives(self) -> Self:
        expected = set(OBJECTIVES) - set(UNKNOWN_OBJECTIVES)
        if set(self.epsilon) != expected:
            raise ValueError(f"epsilon : un par objectif connu {sorted(expected)}")
        if any(v < 0 for v in self.epsilon.values()):
            raise ValueError("epsilon ≥ 0")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)
