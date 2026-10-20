"""Valeurs incertaines (prompt §65, ADR-0005).

Le résumé paramétrique ``(mean, std, lower, upper)`` du prompt ne suffit pas aux
contraintes probabilistes ``P(d > τ) ≤ ε`` ni à la CVaR de l'objectif robuste
(02 §9, §18). La représentation de référence est donc un ensemble de tirages ;
le résumé en est dérivé. Une valeur sans tirages reste utilisable pour
l'affichage, mais toute probabilité de dépassement lève
:class:`InsufficientEvidence` au lieu d'inventer une loi.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.errors import InsufficientEvidence

# Tolérance numérique relative des comparaisons de bornes (arithmétique flottante).
_REL_TOL = 1e-9


class DistributionType(StrEnum):
    EMPIRICAL = "EMPIRICAL"  # tirages (posterior, ensemble, bootstrap)
    NORMAL = "NORMAL"
    UNIFORM = "UNIFORM"  # ex. identification partielle [τ_L, τ_U]
    POINT = "POINT"  # valeur exacte (constante définie, pas une mesure)
    UNKNOWN = "UNKNOWN"  # bornes seulement, loi non identifiée


class UncertainValue(BaseModel):
    """Valeur incertaine. Interface extensible : ``samples`` est la source de vérité quand présent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mean: float | None
    std: float | None = Field(default=None, ge=0.0)
    lower: float | None = None
    upper: float | None = None
    distribution_type: DistributionType
    samples: tuple[float, ...] | None = None
    interval_level: float | None = Field(default=None, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _check(self) -> Self:
        for name in ("mean", "std", "lower", "upper"):
            v = getattr(self, name)
            if v is not None and not math.isfinite(v):
                raise ValueError(f"{name} non fini")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("lower > upper")
        if self.mean is not None:
            # Tolérance relative : moyenne et quantiles flottants peuvent différer d'un ULP.
            tol = _REL_TOL * max(1.0, abs(self.mean))
            if self.lower is not None and self.mean < self.lower - tol:
                raise ValueError("mean < lower")
            if self.upper is not None and self.mean > self.upper + tol:
                raise ValueError("mean > upper")
        if self.distribution_type is DistributionType.EMPIRICAL and not self.samples:
            raise ValueError("EMPIRICAL exige des tirages")
        if self.distribution_type is DistributionType.UNKNOWN and self.mean is not None:
            raise ValueError("loi UNKNOWN : pas de moyenne, seulement des bornes")
        return self

    # --- constructeurs -----------------------------------------------------

    @classmethod
    def from_samples(cls, samples: list[float] | np.ndarray, level: float = 0.9) -> UncertainValue:
        arr = np.asarray(samples, dtype=float)
        if arr.size == 0 or not np.all(np.isfinite(arr)):
            raise ValueError("tirages vides ou non finis")
        alpha = (1.0 - level) / 2.0
        return cls(
            mean=float(arr.mean()),
            std=float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
            lower=float(np.quantile(arr, alpha)),
            upper=float(np.quantile(arr, 1.0 - alpha)),
            distribution_type=DistributionType.EMPIRICAL,
            samples=tuple(float(x) for x in arr),
            interval_level=level,
        )

    @classmethod
    def exact(cls, value: float) -> UncertainValue:
        """Constante définie (ex. un paramètre de scénario), pas une mesure."""
        return cls(mean=value, std=0.0, lower=value, upper=value,
                   distribution_type=DistributionType.POINT)

    @classmethod
    def bounds(cls, lower: float, upper: float) -> UncertainValue:
        """Identification partielle : seules les bornes sont connues (04 §11)."""
        return cls(mean=None, lower=lower, upper=upper, distribution_type=DistributionType.UNKNOWN)

    # --- requêtes ----------------------------------------------------------

    @property
    def has_samples(self) -> bool:
        return bool(self.samples)

    def exceedance_probability(self, threshold: float) -> float:
        """P(X > threshold). Requiert des tirages, ou une constante."""
        if self.distribution_type is DistributionType.POINT and self.mean is not None:
            return 1.0 if self.mean > threshold else 0.0
        if not self.samples:
            raise InsufficientEvidence(
                "P(X > τ) non calculable sans tirages : loi non identifiée"
            )
        arr = np.asarray(self.samples)
        return float(np.mean(arr > threshold))

    def cvar(self, alpha: float) -> float:
        """CVaR_α de la queue haute (perte) : moyenne des (1−α) pires tirages."""
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha doit être dans ]0,1[")
        if not self.samples:
            raise InsufficientEvidence("CVaR non calculable sans tirages")
        arr = np.sort(np.asarray(self.samples))
        k = max(1, math.ceil((1.0 - alpha) * arr.size))
        return float(arr[-k:].mean())

    def is_within(self, lo: float, hi: float) -> bool:
        """Vrai si tout le support connu est dans [lo, hi] (invariants de type [0,1])."""
        vals = [v for v in (self.lower, self.upper, self.mean) if v is not None]
        if self.samples:
            vals.extend((min(self.samples), max(self.samples)))
        tol = _REL_TOL * max(1.0, abs(lo), abs(hi))
        return all(lo - tol <= v <= hi + tol for v in vals)
