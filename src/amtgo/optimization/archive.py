"""Construction de l'archive à partir des évaluations par ω (M10, factorisée en M11).

Fonctions pures : la même construction sert à l'archive nominale, à la
sensibilité normative (S^parameter, 05 §18), aux régimes (05 §19), aux
archives par maillage (05 §5) et aux ablations (05 §13). Une variante porte
ses valeurs par ω = (maillage, ontologie) ; on les agrège par ρ, on trie par
ε-dominance, puis on compare au statu quo.

Comparaison au statu quo (M11) : une option ne « domine » le statu quo que si
elle le domine sur les objectifs connus (hors transition, Map-R) **et** si
chaque objectif UNKNOWN est tranché en sa faveur par un axiome structurel
(``unknown_vs_status_quo``). Sinon la dominance reste non résolue : ignorer un
objectif inconnu pour départager l'archive est admis, s'en servir pour
conclure ne l'est pas.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from amtgo.manifests.normative import RobustnessWeights
from amtgo.optimization.objectives import (
    OBJECTIVES,
    UNKNOWN_OBJECTIVES,
    SqRelation,
    UnknownBound,
    unknown_vs_status_quo,
)
from amtgo.optimization.pareto import Solution, eps_dominates, infeasibility_certificate, nondominated_sort, robust

BASELINE_FAMILIES = ("STATUS_QUO", "NO_TERRITORIAL_CHANGE", "INSTITUTIONAL_ONLY_REFORM")

Omega = tuple[str, str]  # (maillage, ontologie)


@dataclass(frozen=True)
class Variant:
    key: str
    family: str
    params: dict[str, Any]
    omega: dict[Omega, dict[str, Any]]  # objectifs et « violations » par ω
    contiguous: bool = True
    relation: SqRelation = SqRelation.CROSSING  # au statu quo, sur tous les maillages

    @property
    def baseline(self) -> bool:
        return self.family in BASELINE_FAMILIES

    def with_omega(self, fn: Callable[[Omega, dict[str, Any]], dict[str, Any]]) -> Variant:
        return replace(self, omega={w: fn(w, v) for w, v in self.omega.items()})

    def restricted(self, keep: Callable[[Omega], bool]) -> Variant:
        return replace(self, omega={w: v for w, v in self.omega.items() if keep(w)})


@dataclass
class Archive:
    solutions: list[Solution]
    conclusion: str
    improving: list[str]  # dominent le statu quo, inconnus tranchés en leur faveur
    unresolved: dict[str, dict[str, str]]  # dominent sur les connus ; bornes des inconnus
    certificate: dict[str, Any] | None
    objectives: tuple[str, ...] = OBJECTIVES
    status: dict[str, tuple[bool, bool]] = field(default_factory=dict)  # clé → (faisable, au front)

    @property
    def front(self) -> list[str]:
        return sorted(s.key for s in self.solutions if s.rank == 1)


def to_solutions(variants: list[Variant], robustness: RobustnessWeights,
                 objectives: tuple[str, ...] = OBJECTIVES) -> list[Solution]:
    sols = []
    for v in variants:
        violated = {f"{x} (ω={m}/{o})" for (m, o), w in v.omega.items() for x in w["violations"]}
        if not v.contiguous:
            violated.add("contiguïté")
        if not v.omega:
            violated.add("aucune évaluation")
        vals: dict[str, float | None] = {}
        for k in dict.fromkeys((*OBJECTIVES, *objectives)):
            xs = [w[k] for w in v.omega.values() if w.get(k) is not None]
            known = k in objectives and k not in UNKNOWN_OBJECTIVES and xs and len(xs) == len(v.omega)
            vals[k] = robust(xs, robustness) if known else None
        sols.append(Solution(v.key, v.family, v.params, vals, feasible=not violated, violated=sorted(violated),
                             baseline=v.baseline))
    return sols


def build(variants: list[Variant], eps: dict[str, float], robustness: RobustnessWeights,
          normative: dict[str, Any], objectives: tuple[str, ...] = OBJECTIVES,
          sq_comparison_excludes: tuple[str, ...] = ("J_T",)) -> Archive:
    sols = to_solutions(variants, robustness, objectives)
    eps = {k: x for k, x in eps.items() if k in objectives}
    nondominated_sort(sols, eps)
    certificate = infeasibility_certificate(sols, normative)
    sq = next(s for s in sols if s.family == "STATUS_QUO")
    relation = {v.key: v.relation for v in variants}
    # Archive M10 : comparaison au statu quo hors transition ; Map-R (M12) la réintègre.
    # Le changement a un coût : J + C_transition (02 §20).
    eps_wo_t = {k: x for k, x in eps.items() if k not in sq_comparison_excludes}
    improving, unresolved = [], {}
    for s in sols:
        if not s.feasible or s.baseline or not eps_dominates(s.objectives, sq.objectives, eps_wo_t):
            continue
        bounds = {u: unknown_vs_status_quo(u, relation[s.key]) for u in UNKNOWN_OBJECTIVES if u in objectives}
        if all(b in (UnknownBound.EQUAL, UnknownBound.NOT_WORSE) for b in bounds.values()):
            improving.append(s.key)
        else:
            unresolved[s.key] = {u: b.value for u, b in bounds.items()}
    if certificate is not None:
        conclusion = "INFEASIBLE"
    elif improving:
        conclusion = "TERRITORIAL_OPTIONS_DOMINATE_STATUS_QUO_EXCEPT_TRANSITION"
    elif unresolved:
        conclusion = "DOMINANCE_UNRESOLVED_UNKNOWN_OBJECTIVES"
    else:
        conclusion = "NO_TERRITORIAL_CHANGE"
    return Archive(sols, conclusion, sorted(improving), dict(sorted(unresolved.items())), certificate, objectives,
                   {s.key: (s.feasible, s.rank == 1) for s in sols})
