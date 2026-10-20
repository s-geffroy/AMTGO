"""État social évalué par D/F/I, et interface des identités endogènes (prompt §18-21).

``SocialState`` réunit, sous UNE ontologie :
- les effectifs par groupe et par cellule, en tirages (S, N, G) ;
- des **noyaux de liens** par canal (matrices creuses cellule × cellule) :
  ``R^c_ij`` est l'intensité des liens par paire de personnes ; les liens d'un
  groupe g entre i et j valent R^c_ij · n_gi · n_gj ;
- des liens propres à un groupe (ex. flux pastoraux), prioritaires ;
- la **qualité** des contacts entre groupes, par canal d'intégration ;
- l'**identité nationale**, séparée (prompt §21) : distribution, par cellule et
  par groupe, sur une ontologie nationale. Elle module la cohésion culturelle
  (deux personnes partagent une cohésion culturelle d'autant plus forte
  qu'elles partagent la même identité nationale) — elle n'est jamais déduite
  de l'appartenance ethnoculturelle.

Un canal sans données est **absent** du dictionnaire : ses métriques sont
UNKNOWN, jamais 0 (prompt §33). En particulier, le canal territorial exige un
**attachement territorial** observé (01 §28) : la seule contiguïté d'un groupe
n'est pas un lien, et compter sa coupure reviendrait à fragmenter un groupe
« parce qu'il apparaît dans deux États » (prompt §23).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from scipy import sparse

from amtgo.core.channels import FragChannel, IntegChannel
from amtgo.core.enums import PrivacyClass
from amtgo.core.uncertainty import UncertainValue
from amtgo.errors import CausalUnsupported


@dataclass
class SocialState:
    ontology_id: str
    cell_ids: list[str]
    groups: list[str]
    population: np.ndarray  # (S, N, G)
    ties: dict[FragChannel, sparse.csr_matrix] = field(default_factory=dict)
    group_ties: dict[tuple[FragChannel, str], sparse.csr_matrix] = field(default_factory=dict)
    exposure: dict[IntegChannel, sparse.csr_matrix] = field(default_factory=dict)
    quality: dict[IntegChannel, np.ndarray] = field(default_factory=dict)  # (G, G) ∈ [0,1]
    national_identity: np.ndarray | None = None  # (N, G, K_nat), lignes stochastiques
    privacy_class: PrivacyClass = PrivacyClass.CONTROLLED
    assumptions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _, n, g = self.population.shape
        if n != len(self.cell_ids) or g != len(self.groups):
            raise ValueError("SocialState : dimensions incohérentes")
        if np.any(self.population < 0):
            raise ValueError("SocialState : effectifs négatifs")
        for name, m in [*self.ties.items(), *self.exposure.items(), *self.group_ties.items()]:
            if m.shape != (n, n):
                raise ValueError(f"SocialState : noyau {name} de forme {m.shape}")
        for c, q in self.quality.items():
            if q.shape != (g, g) or np.any((q < 0) | (q > 1)):
                raise ValueError(f"SocialState : qualité {c} invalide")
        if self.national_identity is not None:
            ni = self.national_identity
            if ni.shape[:2] != (n, g) or not np.allclose(ni.sum(axis=2), 1.0):
                raise ValueError("SocialState : identité nationale invalide")
        # Les attributs de groupe ne sont jamais publics (prompt §50, 06 §10).
        if self.privacy_class.rank < PrivacyClass.CONTROLLED.rank:
            raise ValueError("SocialState : classe d'accès inférieure à CONTROLLED")

    @property
    def n_samples(self) -> int:
        return int(self.population.shape[0])

    def group_index(self, g: str) -> int:
        return self.groups.index(g)


# --- Identités endogènes (prompt §18) -------------------------------------------------


class IdentityTransition(Protocol):
    """E_{t+1} = f(E_t, institutions_t, competition_t, national_identity_t, integration_t, ε_t).

    ``salience_response`` renvoie, pour un changement d'institutionnalisation Δ,
    l'effet sur la saillance politique à l'horizon H. Sans support causal, une
    implémentation doit lever CausalUnsupported plutôt qu'inventer un coefficient.
    """

    def salience_response(self, delta_institutionalization: float, horizon_years: float) -> UncertainValue: ...


class StaticIdentity:
    """Identités supposées constantes. Hypothèse explicite (WE ASSUME), pas un résultat."""

    assumption = "identités statiques (aucune dynamique endogène modélisée)"

    def salience_response(self, delta_institutionalization: float, horizon_years: float) -> UncertainValue:
        raise CausalUnsupported(
            "identités statiques : l'effet des institutions sur la saillance est CAUSAL_EFFECT_UNKNOWN")


@dataclass(frozen=True)
class BoundedSalienceResponse:
    """Réponse linéaire bornée : ΔS = β · Δ_inst · H / H_ref, β ∈ [β_lo, β_hi].

    Les bornes sont **exploratoires** (identification partielle, 04 §11) tant que
    la bibliothèque causale (M7) ne fournit pas d'effet gelé. Le résultat est un
    intervalle, jamais un point.
    """

    beta_lo: float
    beta_hi: float
    reference_horizon_years: float
    source: str  # provenance des bornes (ex. "hypothèse d'expert I7, non causale")

    def salience_response(self, delta_institutionalization: float, horizon_years: float) -> UncertainValue:
        k = delta_institutionalization * horizon_years / self.reference_horizon_years
        lo, hi = sorted((self.beta_lo * k, self.beta_hi * k))
        return UncertainValue.bounds(lo, hi)
