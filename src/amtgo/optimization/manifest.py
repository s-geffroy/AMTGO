"""OptimizerManifest : paramètres de l'optimiseur régional (M10), figés dans le RunManifest.

M11 y ajoute la grille de **sensibilité normative** (05 §18 : un paramètre à la
fois, S^parameter) et les seuils des **détecteurs Goodhart** (05 §14). Ces seuils
sont des diagnostics qui signalent une variante pour revue humaine (01 §17) :
ils n'excluent rien et ne pondèrent rien — il n'existe aucun seuil universel de
taille d'État (01 §8).
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.manifests.normative import RobustnessWeights
from amtgo.optimization.objectives import OBJECTIVES, UNKNOWN_OBJECTIVES
from amtgo.utils.canonical import content_hash


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SensitivitySpec(_Strict):
    """Valeurs alternatives, chacune testée seule, les autres paramètres restant nominaux."""

    severe_domination_threshold: tuple[float, ...] = ()
    severe_domination_probability_max: tuple[float, ...] = ()
    robustness: tuple[RobustnessWeights, ...] = ()
    epsilon_scale: tuple[float, ...] = ()
    border_cost_per_km: tuple[float, ...] = ()

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        probs = (*self.severe_domination_threshold, *self.severe_domination_probability_max)
        if any(not 0.0 <= x <= 1.0 for x in probs):
            raise ValueError("seuils de domination dans [0, 1]")
        if any(x <= 0 for x in self.epsilon_scale) or any(x < 0 for x in self.border_cost_per_km):
            raise ValueError("epsilon_scale > 0 et border_cost_per_km ≥ 0")
        return self

    @property
    def size(self) -> int:
        return (len(self.severe_domination_threshold) + len(self.severe_domination_probability_max)
                + len(self.robustness) + len(self.epsilon_scale) + len(self.border_cost_per_km))


class GoodhartThresholds(_Strict):
    """Détecteurs d'attaques du solveur (05 §14) : signalement, jamais exclusion. PROVISOIRES."""

    micro_state_population_share: float = Field(gt=0, lt=1)  # micro-territoires
    micro_state_area_share: float = Field(gt=0, lt=1)  # métropoles artificielles, enclaves
    min_compactness: float = Field(gt=0, lt=1)  # Polsby–Popper : formes pathologiques
    max_border_protrusion_share: float = Field(gt=0, lt=1)  # cellules en saillie : frontières en dents de scie


class OptimizerManifest(_Strict):
    optimizer_id: str
    version: str
    description: str
    # Résolution de l'ε-dominance par objectif : un écart plus petit ne départage jamais (ADR-0009).
    epsilon: dict[str, float]
    border_cost_per_km: float = Field(ge=0)  # gestion des frontières, unités du jeu fiscal (PROVISOIRE)
    benchmark_tolerance: float = Field(gt=0, lt=1)  # écart relatif admis au benchmark exact (Gate O)
    sensitivity: SensitivitySpec = SensitivitySpec()
    goodhart: GoodhartThresholds | None = None

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
