"""Domination par domaine (prompt §22, 02 §9, ADR-0006).

Pour le groupe g, la juridiction k et le domaine d :

    D^pot = A_kd · X_gkd · (1 − C_kd)
    X_gkd = 1 − pouvoir effectif du groupe (règle de décision, représentation)
    D^real = q^inst · D^obs              (UNKNOWN sans observation, jamais 0)

Les deux composantes sont conservées ; ``max`` n'est qu'une vue dérivée. La
contrainte de droits s'applique à **chaque** composante connue :
P(d > τ) ≤ ε (02 §9). L'exception d'urgence est repérée quand
P(d > τ_urgent) > p_urgent (02 §27).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from amtgo.core.uncertainty import UncertainValue
from amtgo.geo.partition import Partition
from amtgo.identity.state import SocialState
from amtgo.institutions.competences import Domain, Institution
from amtgo.manifests.normative import RightsThresholds


@dataclass(frozen=True)
class DominationEstimate:
    group: str
    jurisdiction: str
    level: str
    domain: Domain
    population_share: UncertainValue
    potential: UncertainValue
    realized: UncertainValue | None  # None : D_obs non observé → UNKNOWN
    p_exceed: float  # max_composantes P(d > τ)
    p_urgent: float
    violation: bool
    urgent: bool

    @property
    def derived_max_mean(self) -> float:
        """Vue dérivée max(D^pot, D^real) en moyenne, quand D^real est connu."""
        pot = self.potential.mean or 0.0
        real = self.realized.mean if self.realized is not None and self.realized.mean is not None else 0.0
        return max(pot, real)


@dataclass(frozen=True)
class ObservedDomination:
    """D^obs observé (ex. discrimination perçue) et q^inst, part attribuable à l'institution."""

    group: str
    jurisdiction: str
    domain: Domain
    d_obs: UncertainValue
    q_inst: float


def domination(state: SocialState, partition: Partition, institutions: dict[str, list[Institution]],
               rights: RightsThresholds, observed: list[ObservedDomination] | None = None
               ) -> list[DominationEstimate]:
    """``institutions`` : par niveau de la partition, une institution par juridiction (même ordre)."""
    obs_by_key = {(o.group, o.jurisdiction, o.domain): o for o in observed or []}
    tau, eps = rights.severe_domination_threshold, rights.severe_domination_probability_max
    tau_u, p_u = rights.urgent_domination_threshold, rights.urgent_probability
    out: list[DominationEstimate] = []
    total = state.population.sum(axis=2)  # (S, N)
    for level in partition.levels:
        insts = institutions.get(level.name, [])
        if len(insts) != len(level.jurisdictions):
            raise ValueError(f"niveau {level.name} : une institution par juridiction attendue")
        for k, inst in enumerate(insts):
            mask = level.assignment == k
            pop_k = total[:, mask].sum(axis=1)
            for gi, g in enumerate(state.groups):
                n_gk = state.population[:, mask, gi].sum(axis=1)
                if not np.any(n_gk > 0):
                    continue  # groupe absent de la juridiction : personne n'y est dominé
                share = np.divide(n_gk, pop_k, out=np.zeros_like(n_gk), where=pop_k > 0)
                for d in Domain:
                    a = inst.competences.get(d)
                    if a == 0.0:
                        continue
                    rep = _representation(inst, g, d, share)
                    power = np.minimum(1.0, rep / (1.0 - inst.rule(d).threshold))
                    if g in inst.rule(d).veto_groups:
                        power = np.ones_like(power)
                    pot = a * (1.0 - power) * (1.0 - inst.rights.get(d))
                    o = obs_by_key.get((g, inst.jurisdiction_id, d))
                    real = None
                    comps = [pot]
                    if o is not None and o.d_obs.samples:
                        r = o.q_inst * np.resize(np.asarray(o.d_obs.samples), len(pot))
                        real = UncertainValue.from_samples(r)
                        comps.append(r)
                    p_exc = max(float(np.mean(c > tau)) for c in comps)
                    p_urg = max(float(np.mean(c > tau_u)) for c in comps)
                    out.append(DominationEstimate(
                        g, inst.jurisdiction_id, level.name, d, UncertainValue.from_samples(share),
                        UncertainValue.from_samples(pot), real, p_exc, p_urg, p_exc > eps, p_urg > p_u))
    return out


def _representation(inst: Institution, group: str, d: Domain, share: np.ndarray) -> np.ndarray:
    rep = inst.representation
    if group in rep.excluded.get(d, ()):
        return np.zeros_like(share)
    if rep.rule == "fixed" and group in rep.fixed.get(d, {}):
        return np.full_like(share, rep.fixed[d][group])
    return share
