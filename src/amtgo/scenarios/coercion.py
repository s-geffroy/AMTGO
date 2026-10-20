"""Diagnostic S2C : dépendance agrégée d'un bénéfice à la coercition (prompt §37, §93 ; 06 §8).

Question posée : *quelle part du bénéfice apparent d'une configuration n'existe
que si des personnes étaient déplacées ?* La réponse est un nombre agrégé, avec
son intervalle. Elle ne dit jamais **qui**, **où**, **vers où** ni **comment**.

Entrées : effectifs par **juridiction** et par groupe (jamais par cellule) sous la
population atteignable sans coercition et sous la population que le bénéfice
supposerait, et les bénéfices correspondants. Sorties (exactement §93) :

- ``aggregate_population_equivalent`` : nombre minimal de personnes à déplacer
  pour passer d'une répartition à l'autre, Σ_g Σ_k max(0, c_kg − t_kg) — une
  borne agrégée qui ne nécessite aucun appariement origine/destination ;
- ``apparent_homogeneity_gain`` : variation de l'indice de Simpson pondéré
  (probabilité que deux résidents d'une juridiction partagent un groupe) — un
  **diagnostic** du mécanisme, jamais un objectif ;
- ``ratio`` : part du bénéfice qui dépend de la coercition ;
- ``confidence`` : grade déclaré.

Aucune fonction de ce module ne maximise ni ne cherche une répartition : elles
évaluent deux répartitions données. Les tableaux d'entrée ne sont jamais
conservés ; seul le résumé agrégé sort.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from amtgo.core.uncertainty import UncertainValue
from amtgo.errors import InsufficientEvidence


@dataclass(frozen=True)
class CoercionDependencyDiagnostic:
    aggregate_population_equivalent: UncertainValue
    apparent_homogeneity_gain: UncertainValue
    ratio: UncertainValue
    confidence: str

    def to_aggregate_dict(self) -> dict[str, Any]:
        """Résumé publiable en CONTROLLED : moyennes et intervalles seulement, aucun tirage."""
        def s(u: UncertainValue) -> dict[str, float | None]:
            return {"mean": u.mean, "lower": u.lower, "upper": u.upper}
        return {"aggregate_population_equivalent": s(self.aggregate_population_equivalent),
                "apparent_homogeneity_gain": s(self.apparent_homogeneity_gain),
                "ratio": s(self.ratio), "confidence": self.confidence}


def _simpson(counts: np.ndarray) -> np.ndarray:
    """Σ_k Σ_g c_kg² / n_k / N pour chaque tirage ; ``counts`` (S, K, G)."""
    n_k = counts.sum(axis=2)
    total = n_k.sum(axis=1)
    per_k = np.divide((counts**2).sum(axis=2), n_k, out=np.zeros_like(n_k), where=n_k > 0)
    return np.asarray(per_k.sum(axis=1) / total)


def coercion_dependency(feasible: np.ndarray, implied: np.ndarray, benefit_feasible: np.ndarray,
                        benefit_implied: np.ndarray, confidence: str) -> CoercionDependencyDiagnostic:
    if feasible.ndim != 3 or feasible.shape != implied.shape:
        raise ValueError("S2C : effectifs (tirages, juridictions, groupes) attendus, de même forme")
    if feasible.shape[1] < 2:
        raise ValueError("S2C : au moins deux juridictions")
    # Même population par groupe : le diagnostic compare des répartitions, pas des populations.
    if not np.allclose(feasible.sum(axis=1), implied.sum(axis=1), rtol=1e-9, atol=1e-6):
        raise ValueError("S2C : les deux répartitions doivent conserver l'effectif de chaque groupe")
    movers = np.clip(feasible - implied, 0.0, None).sum(axis=(1, 2))
    gain = _simpson(implied) - _simpson(feasible)
    ok = benefit_implied > 0
    if not ok.any():
        raise InsufficientEvidence("S2C : aucun bénéfice apparent, la dépendance n'est pas définie")
    ratio = (benefit_implied[ok] - benefit_feasible[ok]) / benefit_implied[ok]
    return CoercionDependencyDiagnostic(UncertainValue.from_samples(movers), UncertainValue.from_samples(gain),
                                        UncertainValue.from_samples(np.clip(ratio, 0.0, 1.0)), confidence)
