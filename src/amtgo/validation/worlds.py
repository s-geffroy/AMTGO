"""Mondes synthétiques A–F (prompt §56) pour D/F/I.

Chaque monde est un réseau de cellules abstraites (lattice, 10 km de pas), à
vérité connue, avec des **partitions sondes** déclarées — jamais générées
(M8). Les catégories (a, b, m, p…) sont fictives. Les tests vérifient des
**propriétés qualitatives** des composantes D/F/I (ADR-0010) :

- A : deux populations compactes, séparées, peu intégrées → couper entre elles
  rompt peu de connexions valorisées ;
- B : deux populations linguistiquement distinctes mais très intégrées → la même
  coupe rompt beaucoup plus ;
- C : population pastorale traversant trois territoires → forte fragmentation de
  mobilité sous frontières dures, fortement atténuée par un overlay de corridor
  (et par un régime de mobilité) ;
- D : métropole très mixte entourée d'arrière-pays homogènes → couper la
  métropole rompt plus que la laisser entière ;
- E : groupe numériquement majoritaire mais institutionnellement exclu → D > 0,
  contrainte de droits violée, levée par des garde-fous ou la représentation ;
- F : même ethnonyme des deux côtés d'une frontière, identités nationales
  distinctes et liens faibles → F ≈ 0 ; avec identité partagée et liens forts → F > 0.

Les σ* attendus du prompt (« σ* > 0 », « overlay, pas État continu »…) relèvent
de l'optimiseur (M10) ; M5 vérifie les composantes qui les fonderont.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from scipy import sparse

from amtgo.core.channels import FragChannel, IntegChannel
from amtgo.geo.partition import BorderDim, BorderVector, Partition, PartitionLevel
from amtgo.identity.state import SocialState
from amtgo.infrastructure.hyperedges import Hyperedge, HyperedgeType
from amtgo.institutions.competences import (
    CompetenceVector,
    DecisionRule,
    Domain,
    Institution,
    Representation,
    RightsProfile,
)

SPACING_KM = 10.0
KERNEL_LENGTH_KM = 12.0
N_SAMPLES = 200


def border(**dims: float) -> BorderVector:
    """Frontière : chaque dimension nommée (P, C, E, M, R, S), 1.0 par défaut (frontière dure)."""
    return BorderVector(strength={d: dims.get(d.value, 1.0) for d in BorderDim})


HARD = border()


@dataclass
class Lattice:
    nx: int
    ny: int

    @property
    def n(self) -> int:
        return self.nx * self.ny

    @property
    def ids(self) -> list[str]:
        return [f"c{x:02d}_{y:02d}" for y in range(self.ny) for x in range(self.nx)]

    @property
    def xy(self) -> np.ndarray:
        return np.array([(x, y) for y in range(self.ny) for x in range(self.nx)], dtype=float) * SPACING_KM

    def adjacency(self) -> sparse.csr_matrix:
        rows, cols = [], []
        for y in range(self.ny):
            for x in range(self.nx):
                i = y * self.nx + x
                for dx, dy in ((1, 0), (0, 1)):
                    if x + dx < self.nx and y + dy < self.ny:
                        j = (y + dy) * self.nx + (x + dx)
                        rows += [i, j]
                        cols += [j, i]
        return sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(self.n, self.n))

    def distance_kernel(self, length_km: float = KERNEL_LENGTH_KM) -> sparse.csr_matrix:
        d = np.linalg.norm(self.xy[:, None, :] - self.xy[None, :, :], axis=2)
        # Paires intra-cellule : distance moyenne ~ 0,5 × pas (indépendant de la maille).
        np.fill_diagonal(d, 0.5 * SPACING_KM)
        k = np.exp(-d / length_km)
        k[d > 3 * length_km] = 0.0
        return sparse.csr_matrix(k)

    def bands(self, cuts: list[int], level: str = "state", b: BorderVector = HARD) -> Partition:
        x = self.xy[:, 0] / SPACING_KM
        assign = np.searchsorted(np.array(cuts), x, side="right")
        names = [f"{level}_{k}" for k in range(len(cuts) + 1)]
        return Partition("lattice", self.ids, [PartitionLevel(level, assign, names, b)])

    def custom(self, fn: Callable[[float, float], int], k: int, level: str = "state",
               b: BorderVector = HARD) -> Partition:
        assign = np.array([fn(x / SPACING_KM, y / SPACING_KM) for x, y in self.xy], dtype=int)
        return Partition("lattice", self.ids, [PartitionLevel(level, assign, [f"{level}_{i}" for i in range(k)], b)])


def _samples(expected: np.ndarray, seed: int) -> np.ndarray:
    """(S, N, G) : tirages de Poisson autour des effectifs attendus (incertitude de comptage)."""
    rng = np.random.default_rng(seed)
    return rng.poisson(expected[None, :, :], size=(N_SAMPLES, *expected.shape)).astype(float)


@dataclass
class World:
    name: str
    state: SocialState
    probes: dict[str, Partition]
    overlays: dict[str, list[Hyperedge]] = field(default_factory=dict)
    institutions: dict[str, dict[str, list[Institution]]] = field(default_factory=dict)


def _state(name: str, lat: Lattice, groups: list[str], expected: np.ndarray, seed: int,
           quality: float = 1.0, **extra: object) -> SocialState:
    k = lat.distance_kernel()
    g = len(groups)
    st = SocialState(ontology_id=f"world_{name}", cell_ids=lat.ids, groups=groups,
                     population=_samples(expected, seed),
                     # Pas de canal territorial par défaut : la contiguïté d'un groupe n'est pas un
                     # lien. Il exige un attachement territorial observé (01 §28) ; sinon UNKNOWN.
                     ties={FragChannel.NETWORK: k},
                     exposure={IntegChannel.SPATIAL: k},
                     quality={IntegChannel.SPATIAL: np.full((g, g), quality)},
                     assumptions=["monde synthétique A–F : effectifs et liens déclarés"])
    for key, val in extra.items():
        setattr(st, key, val)
    return st


def world_a() -> World:
    lat = Lattice(12, 6)
    x = lat.xy[:, 0] / SPACING_KM
    e = np.zeros((lat.n, 2))
    e[x < 5, 0] = 200.0   # a, compact à l'ouest
    e[x >= 7, 1] = 200.0  # b, compact à l'est ; deux colonnes quasi vides entre eux
    e[(x >= 5) & (x < 7), :] = 2.0
    st = _state("A", lat, ["a", "b"], e, 1, quality=0.3)
    return World("A", st, {"split": lat.bands([6]), "unified": lat.bands([])})


def world_b() -> World:
    lat = Lattice(12, 6)
    e = np.full((lat.n, 2), 100.0)  # a et b mêlés partout, contacts de bonne qualité
    st = _state("B", lat, ["a", "b"], e, 2, quality=0.9)
    return World("B", st, {"split": lat.bands([6]), "unified": lat.bands([])})


def world_c() -> World:
    lat = Lattice(15, 7)
    x, y = lat.xy[:, 0] / SPACING_KM, lat.xy[:, 1] / SPACING_KM
    e = np.zeros((lat.n, 2))
    corridor = np.abs(y - 3) <= 1
    e[corridor, 0] = 60.0  # p : pastoraux le long du corridor
    e[:, 1] = 150.0  # f : agriculteurs partout
    # Liens de mobilité des pastoraux : déplacements saisonniers le long du corridor (portée longue).
    ids = np.where(corridor)[0]
    rows, cols, vals = [], [], []
    for i in ids:
        for j in ids:
            if i != j:
                rows.append(i)
                cols.append(j)
                vals.append(np.exp(-abs(x[i] - x[j]) / 6.0))
    pastoral = sparse.csr_matrix((vals, (rows, cols)), shape=(lat.n, lat.n))
    st = _state("C", lat, ["p", "f"], e, 3)
    st.group_ties[(FragChannel.MOBILITY, "p")] = pastoral
    st.group_ties[(FragChannel.MOBILITY, "f")] = lat.adjacency() * 0.05  # mobilité locale faible
    # Attachement territorial observé des pastoraux aux pâturages du corridor (01 §28).
    st.group_ties[(FragChannel.TERRITORIAL, "p")] = pastoral
    members = tuple(np.array(lat.ids)[corridor])
    overlay = Hyperedge(hyperedge_id="corridor", type=HyperedgeType.PASTORAL, members=members,
                        groups=("p",),
                        # Overlay pastoral : liberté de passage ET droits d'accès aux pâturages.
                        mitigation={FragChannel.MOBILITY: 0.9, FragChannel.TERRITORIAL: 0.9})
    three_hard = lat.bands([5, 10])
    three_soft = lat.bands([5, 10], b=border(M=0.2))
    return World("C", st, {"three_hard": three_hard, "three_hard_overlay": three_hard,
                           "three_soft_mobility": three_soft},
                 overlays={"three_hard_overlay": [overlay]})


def world_d() -> World:
    lat = Lattice(15, 9)
    x, y = lat.xy[:, 0] / SPACING_KM, lat.xy[:, 1] / SPACING_KM
    r = np.hypot(x - 7, y - 4)
    metro = r <= 2.5
    e = np.zeros((lat.n, 3))
    e[metro, :] = 800.0  # métropole très mixte : a, b, c
    e[~metro & (x < 7), 0] = 80.0  # arrière-pays ouest homogène
    e[~metro & (x > 7), 1] = 80.0  # arrière-pays est homogène
    e[~metro & (x == 7), :2] = 40.0
    st = _state("D", lat, ["a", "b", "c"], e, 4, quality=0.8)
    split_metro = lat.bands([7])

    def whole(xx: float, yy: float) -> int:
        if np.hypot(xx - 7, yy - 4) <= 2.5:
            return 1
        return 0 if xx < 7 else 2

    return World("D", st, {"split_metro": split_metro, "metro_whole": lat.custom(whole, 3)})


def _institution(jid: str, *, checks: float, excluded: tuple[str, ...] = ()) -> Institution:
    return Institution(
        jurisdiction_id=jid, level="state",
        competences=CompetenceVector(authority={Domain.EXECUTIVE_POWER: 1.0, Domain.SECURITY: 1.0,
                                                Domain.PUBLIC_EMPLOYMENT: 1.0}),
        decision={}, default_decision=DecisionRule(threshold=0.5),
        rights=RightsProfile(checks={}, default=checks),
        representation=Representation(rule="proportional",
                                      excluded={Domain.EXECUTIVE_POWER: excluded} if excluded else {}))


def world_e() -> World:
    lat = Lattice(10, 6)
    e = np.zeros((lat.n, 2))
    e[:, 0] = 140.0  # m : 70 % de la population
    e[:, 1] = 60.0   # n : 30 %
    st = _state("E", lat, ["m", "n"], e, 5)
    unified = lat.bands([])
    return World("E", st, {"excluded": unified, "excluded_with_rights": unified, "inclusive": unified},
                 institutions={
                     "excluded": {"state": [_institution("state_0", checks=0.2, excluded=("m",))]},
                     "excluded_with_rights": {"state": [_institution("state_0", checks=0.95, excluded=("m",))]},
                     "inclusive": {"state": [_institution("state_0", checks=0.5)]},
                 })


def world_f(shared_identity: bool = False, strong_ties: bool = False) -> World:
    lat = Lattice(12, 6)
    x = lat.xy[:, 0] / SPACING_KM
    e = np.zeros((lat.n, 1))
    e[:, 0] = 100.0  # un seul ethnonym « x », des deux côtés
    nat = np.zeros((lat.n, 1, 2))
    if shared_identity:
        nat[:, 0, 0] = 1.0
    else:
        nat[x < 6, 0, 0] = 1.0  # identité nationale N1 à l'ouest
        nat[x >= 6, 0, 1] = 1.0  # N2 à l'est
    cultural = lat.distance_kernel(KERNEL_LENGTH_KM)
    network = lat.distance_kernel()
    if not strong_ties:
        # Liens transfrontaliers faibles : la frontière historique a déjà séparé les réseaux.
        coo = network.tocoo()
        cross = (x[coo.row] < 6) != (x[coo.col] < 6)
        data = coo.data.copy()
        data[cross] *= 0.02
        network = sparse.csr_matrix((data, (coo.row, coo.col)), shape=network.shape)
    st = _state("F", lat, ["x"], e, 6)
    st.ties[FragChannel.NETWORK] = network
    st.ties[FragChannel.CULTURAL] = cultural
    st.national_identity = nat
    return World("F", st, {"current_border": lat.bands([6])})


WORLDS = {"A": world_a, "B": world_b, "C": world_c, "D": world_d, "E": world_e, "F": world_f}
