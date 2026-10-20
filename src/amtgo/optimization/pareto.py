"""Archive de Pareto robuste, ε-dominance, infaisabilité (prompt §41-44, 02 §17-18, §33, ADR-0009).

- ρ(J) = E_ω[J] + λ_tail·CVaR_α(J) + λ_var·Var_ω(J) sur ω = (ontologie, maillage, …) ;
- ε-dominance (minimisation) : a domine b si a n'est pire nulle part au-delà de ε
  et meilleur quelque part au-delà de ε — les écarts sous la résolution ε ne
  départagent jamais ;
- un objectif UNKNOWN pour une solution ne lui est jamais compté à 0 : la
  comparaison se fait sur les seuls objectifs connus des deux, et l'archive
  indique ceux qui ont été ignorés ;
- jamais une seule « meilleure » solution : des rangs, un front, des écarts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from amtgo.manifests.normative import RobustnessWeights


def robust(values: list[float], w: RobustnessWeights) -> float:
    """ρ sur un ensemble de valeurs ω (queue haute = pire, minimisation)."""
    arr = np.sort(np.asarray(values, dtype=float))
    k = max(1, math.ceil((1.0 - w.cvar_alpha) * arr.size))
    cvar = float(arr[-k:].mean())
    var = float(arr.var()) if arr.size > 1 else 0.0
    return float(arr.mean()) + w.lambda_tail * cvar + w.lambda_var * var


@dataclass
class Solution:
    key: str
    family: str
    params: dict[str, Any]
    objectives: dict[str, float | None]  # ρ par objectif ; None : UNKNOWN
    feasible: bool
    violated: list[str] = field(default_factory=list)  # contraintes dures liantes
    rank: int | None = None
    baseline: bool = False


def eps_dominates(a: dict[str, float | None], b: dict[str, float | None], eps: dict[str, float]) -> bool:
    known = [k for k in eps if a.get(k) is not None and b.get(k) is not None]
    if not known:
        return False
    not_worse = all(a[k] <= b[k] + eps[k] for k in known)  # type: ignore[operator]
    better = any(a[k] < b[k] - eps[k] for k in known)  # type: ignore[operator]
    return not_worse and better


def nondominated_sort(sols: list[Solution], eps: dict[str, float]) -> None:
    """Rangs de Pareto (1 = front) des solutions faisables ; les infaisables restent sans rang."""
    pool = [s for s in sols if s.feasible]
    rank = 1
    while pool:
        front = [s for s in pool if not any(eps_dominates(o.objectives, s.objectives, eps) for o in pool if o is not s)]
        if not front:  # cycle impossible avec une ε-dominance stricte ; garde-fou
            front = pool
        for s in front:
            s.rank = rank
        pool = [s for s in pool if s not in front]
        rank += 1


def infeasibility_certificate(sols: list[Solution], normative: dict[str, Any]) -> dict[str, Any] | None:
    """Prompt §43 : si aucune solution n'est faisable, INFEASIBLE avec contraintes liantes et conflits minimaux.

    Ensemble de conflit minimal (approché) : pour chaque solution, l'ensemble des
    contraintes qu'elle viole ; les plus petits de ces ensembles sont les
    relaxations minimales qui rendraient une solution faisable. Aucune n'est appliquée.
    """
    if any(s.feasible for s in sols):
        return None
    binding: dict[str, int] = {}
    for s in sols:
        for c in s.violated:
            binding[c] = binding.get(c, 0) + 1
    smallest = min((len(s.violated) for s in sols), default=0)
    conflicts = sorted({tuple(sorted(s.violated)) for s in sols if len(s.violated) == smallest})
    return {"status": "INFEASIBLE", "binding_constraints": dict(sorted(binding.items(), key=lambda x: -x[1])),
            "minimal_conflict_sets": [list(c) for c in conflicts], "normative_parameters": normative,
            "relaxation_applied": False}
