"""SCM historique de Map-C-Deep (02 §22, 04 §20-21, 01 §6) — branche de recherche.

Map-C-Deep demande comment les sociétés auraient pu évoluer sous une autre histoire
institutionnelle :

    X_2026^cf = f_θ(X_historique, A_historique^cf)

Exigences de la spec :
- **un SCM historique séparé**, estimé sur des données historiques seulement ;
- **jamais** extrapoler les coefficients contemporains sur 150 ans ; ce module
  n'importe pas la bibliothèque causale et n'en reçoit aucun effet ;
- validation : temporal holdout, leave-region-out, placebo (04 §21) ;
- statut : contre-factuel historique, non prescriptif.

Le SCM est volontairement petit. Pas de 10 ans, cellules d'un treillis. Les
institutions historiques A_t sont une affectation des cellules à des entités
politiques et une capitale par entité.

1. Croissance naturelle uniforme (estimée sur les totaux observés).
2. Migration volontaire : une part μ de chaque cellule migre vers j selon
   w_ij = K_mig(d_ij) · (P_j+1)^α · (1 + γ·C_j) · (1 − β·[i,j séparés par une frontière]),
   où C_j est la proximité d'une capitale. Les groupes migrent avec leurs parts :
   le modèle n'attribue aucun territoire à un groupe.
3. Identification à l'entité d'appartenance S ∈ [0,1] : un migrant qui change
   d'entité perd une part λ de la sienne, de même qu'une cellule qui change
   d'entité ; puis S croît vers 1 au taux ν (construction nationale).

θ = (μ, α, γ, β, ν, λ). La forme structurelle est incertaine : plusieurs modèles
(avec ou sans friction frontalière) sont estimés, et seuls ceux qui passent la
validation forment l'ensemble. Aucun déplacement forcé : A^cf ne change que des
frontières et des capitales.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np
from scipy.optimize import least_squares

STEP_YEARS = 10
PARAMS = ("mu", "alpha", "gamma", "beta", "nu", "lam")
BOUNDS = {"mu": (0.0, 0.5), "alpha": (0.0, 2.0), "gamma": (0.0, 10.0), "beta": (0.0, 1.0),
          "nu": (0.0, 1.0), "lam": (0.0, 1.0)}


class Model(StrEnum):
    BORDER_FRICTION = "border_friction"
    NO_BORDER_FRICTION = "no_border_friction"  # β = 0 : la frontière ne freine pas la migration


@dataclass(frozen=True)
class Period:
    start: int
    assignment: np.ndarray  # entité politique de chaque cellule
    capitals: tuple[int, ...]  # cellule capitale de chaque entité


@dataclass(frozen=True)
class History:
    periods: tuple[Period, ...]

    def at(self, year: int) -> Period:
        return [p for p in self.periods if p.start <= year][-1]


@dataclass(frozen=True)
class Geography:
    xy: np.ndarray  # (N, 2) km
    blocks: np.ndarray  # bloc d'observation de chaque cellule
    k_mig: np.ndarray  # noyau de migration, diagonale nulle
    k_cap: np.ndarray  # proximité d'une capitale (N, N)
    k_tie: np.ndarray  # noyau de liens (indicateurs)

    @property
    def n(self) -> int:
        return len(self.xy)

    @property
    def n_blocks(self) -> int:
        return int(self.blocks.max()) + 1

    def block_sum(self, v: np.ndarray) -> np.ndarray:
        out = np.zeros((self.n_blocks, *v.shape[1:]))
        np.add.at(out, self.blocks, v)
        return out


def geography(nx: int, ny: int, spacing_km: float, block: tuple[int, int], mig_km: float, cap_km: float,
              tie_km: float) -> Geography:
    xs, ys = np.meshgrid(np.arange(nx), np.arange(ny))
    xy = np.column_stack([xs.ravel(), ys.ravel()]).astype(float) * spacing_km
    bx, by = block
    blocks = (ys.ravel() // by) * ((nx + bx - 1) // bx) + xs.ravel() // bx
    d = np.linalg.norm(xy[:, None, :] - xy[None, :, :], axis=2)
    k_mig = np.exp(-d / mig_km)
    np.fill_diagonal(k_mig, 0.0)
    k_mig[d > 4 * mig_km] = 0.0
    k_tie = np.exp(-d / tie_km)
    k_tie[d > 3 * tie_km] = 0.0
    np.fill_diagonal(k_tie, 0.0)
    return Geography(xy, blocks.astype(int), k_mig, np.exp(-d / cap_km), k_tie)


@dataclass(frozen=True)
class Trajectory:
    population: dict[int, np.ndarray]  # année → (N, G)
    identity: dict[int, np.ndarray]  # année → (N,)


def simulate(theta: dict[str, float], geo: Geography, history: History, p0: np.ndarray, s0: np.ndarray,
             growth: float, start: int, end: int, placebo: tuple[np.ndarray, int] | None = None,
             beta_placebo: float = 0.0) -> Trajectory:
    """Déroule le SCM de ``start`` à ``end``. ``placebo`` : (côté de chaque cellule, année d'effet)."""
    p, s = p0.astype(float).copy(), s0.astype(float).copy()
    pops, ids = {start: p.copy()}, {start: s.copy()}
    prev = history.at(start).assignment
    for year in range(start, end, STEP_YEARS):
        per = history.at(year + STEP_YEARS)  # institutions en vigueur pendant la décennie
        poly = per.assignment
        cross = (poly[:, None] != poly[None, :]).astype(float)
        cap = geo.k_cap[:, list(per.capitals)].max(axis=1)
        tot = p.sum(axis=1)
        w = geo.k_mig * ((tot + 1.0) ** theta["alpha"] * (1.0 + theta["gamma"] * cap))[None, :]
        w = w * (1.0 - theta["beta"] * cross)
        if placebo is not None and year + STEP_YEARS > placebo[1]:
            side = placebo[0]
            w = w * (1.0 - beta_placebo * (side[:, None] != side[None, :]))
        wn = w / np.maximum(w.sum(axis=1, keepdims=True), 1e-300)
        mu = theta["mu"]
        moved = mu * wn.T @ p  # (N, G) arrivées
        stay = (1.0 - mu) * p
        new_p = stay + moved
        new_tot = new_p.sum(axis=1)
        carried = mu * (wn * (1.0 - theta["lam"] * cross)).T @ (s * tot)  # identité des migrants
        new_s = (s * stay.sum(axis=1) + carried) / np.maximum(new_tot, 1e-300)
        changed = poly != prev
        new_s[changed] *= 1.0 - theta["lam"]
        new_s = new_s + theta["nu"] * (1.0 - new_s)
        p, s, prev = new_p * (1.0 + growth), np.clip(new_s, 0.0, 1.0), poly
        pops[year + STEP_YEARS], ids[year + STEP_YEARS] = p.copy(), s.copy()
    return Trajectory(pops, ids)


# --- observations historiques ------------------------------------------------------------------

@dataclass(frozen=True)
class Design:
    census_years: tuple[int, ...]
    share_years: tuple[int, ...]
    survey_years: tuple[int, ...]
    noise: dict[str, float]  # census, init, shares, survey


@dataclass(frozen=True)
class Observations:
    start: int
    init_cells: np.ndarray  # (N, G) recensement initial, à la cellule
    census: dict[int, np.ndarray]  # année → totaux par bloc
    shares: dict[int, np.ndarray]  # année → parts de groupes par bloc (B, G)
    survey: dict[int, np.ndarray]  # année → S moyen par bloc
    noise: dict[str, float]


def observe(traj: Trajectory, geo: Geography, design: Design, rng: np.random.Generator) -> Observations:
    nz = design.noise
    start = min(traj.population)
    init = traj.population[start] * np.exp(rng.normal(0.0, nz["init"], traj.population[start].shape))
    census = {y: geo.block_sum(traj.population[y].sum(axis=1)) * np.exp(rng.normal(0.0, nz["census"], geo.n_blocks))
              for y in design.census_years}
    shares = {}
    for y in design.share_years:
        b = geo.block_sum(traj.population[y])
        shares[y] = np.clip(b / b.sum(axis=1, keepdims=True) + rng.normal(0.0, nz["shares"], b.shape), 0.0, 1.0)
    survey = {}
    for y in design.survey_years:
        p = traj.population[y].sum(axis=1)
        survey[y] = np.clip(geo.block_sum(traj.identity[y] * p) / geo.block_sum(p)
                            + rng.normal(0.0, nz["survey"], geo.n_blocks), 0.0, 1.0)
    return Observations(start, init, census, shares, survey, dict(nz))


def initial_state(obs: Observations, geo: Geography) -> tuple[np.ndarray, np.ndarray]:
    """État initial reconstruit des seules observations : recensement initial, enquête initiale par bloc."""
    if obs.start not in obs.survey:
        raise ValueError("Map-C-Deep : aucune enquête d'identification à la date initiale")
    return obs.init_cells, obs.survey[obs.start][geo.blocks]


def observed_growth(obs: Observations, years: set[int]) -> float:
    ys = sorted(y for y in obs.census if y in years)
    if len(ys) < 2:
        raise ValueError("Map-C-Deep : au moins deux recensements sont nécessaires")
    ratio = obs.census[ys[-1]].sum() / obs.census[ys[0]].sum()
    return float(ratio ** (STEP_YEARS / (ys[-1] - ys[0])) - 1.0)


# --- estimation ----------------------------------------------------------------------------------

def free_params(model: Model, placebo: bool) -> list[str]:
    ps = [k for k in PARAMS if not (model is Model.NO_BORDER_FRICTION and k == "beta")]
    return [*ps, "beta_placebo"] if placebo else ps


@dataclass
class Fit:
    model: Model
    theta: dict[str, float]
    se: dict[str, float | None]
    growth: float
    cost: float
    n_obs: int
    placebo: dict[str, float | None] = field(default_factory=dict)


def _residuals(obs: Observations, geo: Geography, traj: Trajectory, years: set[int],
               blocks: np.ndarray) -> np.ndarray:
    nz, out = obs.noise, []
    for y, v in obs.census.items():
        if y in years and y != obs.start:
            pred = geo.block_sum(traj.population[y].sum(axis=1))
            out.append((np.log(pred[blocks] + 1.0) - np.log(v[blocks] + 1.0)) / nz["census"])
    for y, v in obs.shares.items():
        if y in years and y != obs.start:
            b = geo.block_sum(traj.population[y])
            out.append(((b / np.maximum(b.sum(axis=1, keepdims=True), 1e-300))[blocks] - v[blocks]).ravel()
                       / nz["shares"])
    for y, v in obs.survey.items():
        if y in years and y != obs.start:
            p = traj.population[y].sum(axis=1)
            pred = geo.block_sum(traj.identity[y] * p) / np.maximum(geo.block_sum(p), 1e-300)
            out.append((pred[blocks] - v[blocks]) / nz["survey"])
    return np.concatenate(out) if out else np.zeros(0)


def fit(obs: Observations, geo: Geography, history: History, model: Model, years: set[int] | None = None,
        blocks: np.ndarray | None = None, placebo: tuple[np.ndarray, int] | None = None,
        should_stop: Callable[[], None] = lambda: None) -> Fit:
    """Moindres carrés pondérés par le bruit déclaré ; erreurs-types par la jacobienne."""
    years = set(obs.census) | set(obs.shares) | set(obs.survey) if years is None else years
    blocks = np.arange(geo.n_blocks) if blocks is None else blocks
    names = free_params(model, placebo is not None)
    end = max(years)
    p0, s0 = initial_state(obs, geo)
    growth = observed_growth(obs, years)
    lo = np.array([BOUNDS.get(k, (0.0, 1.0))[0] for k in names])
    hi = np.array([BOUNDS.get(k, (0.0, 1.0))[1] for k in names])

    def unpack(x: np.ndarray) -> tuple[dict[str, float], float]:
        th = {k: 0.0 for k in PARAMS}
        th.update({k: float(v) for k, v in zip(names, x, strict=True) if k != "beta_placebo"})
        return th, float(x[names.index("beta_placebo")]) if placebo is not None else 0.0

    def res(x: np.ndarray) -> np.ndarray:
        should_stop()
        th, bp = unpack(x)
        return _residuals(obs, geo, simulate(th, geo, history, p0, s0, growth, obs.start, end, placebo, bp),
                          years, blocks)

    x0 = lo + 0.3 * (hi - lo)
    r = least_squares(res, x0, bounds=(lo, hi), x_scale="jac", max_nfev=400)
    theta, bp = unpack(r.x)
    se: dict[str, float | None] = dict.fromkeys(names)
    jtj = r.jac.T @ r.jac
    if np.linalg.matrix_rank(jtj) == len(names):
        sigma2 = max(1.0, 2.0 * r.cost / max(len(r.fun) - len(names), 1))
        cov = np.linalg.inv(jtj) * sigma2
        se = {k: float(np.sqrt(max(cov[i, i], 0.0))) for i, k in enumerate(names)}
    f = Fit(model, theta, {k: se[k] for k in names if k != "beta_placebo"}, growth, float(r.cost), len(r.fun))
    if placebo is not None:
        f.placebo = {"beta_placebo": bp, "se": se["beta_placebo"]}
    return f


def predict(f: Fit, obs: Observations, geo: Geography, history: History, end: int) -> Trajectory:
    p0, s0 = initial_state(obs, geo)
    return simulate(f.theta, geo, history, p0, s0, f.growth, obs.start, end)


def prediction_error(traj: Trajectory, obs: Observations, geo: Geography, years: set[int],
                     blocks: np.ndarray) -> dict[str, float]:
    """Erreur hors échantillon en unités du bruit déclaré : moyenne quadratique des résidus standardisés.

    ≈ 1 sous un modèle correct, quel que soit le nombre de blocs et d'années (une erreur maximale
    croît avec eux et rejetait la vraie forme une fois sur deux ou trois). L'erreur relative maximale
    des recensements reste publiée, à titre d'information.
    """
    cz, rel, sz = [], [], []
    for y in obs.census:
        if y in years:
            pred = geo.block_sum(traj.population[y].sum(axis=1))[blocks]
            cz.append((np.log(pred + 1.0) - np.log(obs.census[y][blocks] + 1.0)) / obs.noise["census"])
            rel.append(np.abs(pred / obs.census[y][blocks] - 1.0).max())
    for y in obs.survey:
        if y in years:
            p = traj.population[y].sum(axis=1)
            pred = (geo.block_sum(traj.identity[y] * p) / geo.block_sum(p))[blocks]
            sz.append((pred - obs.survey[y][blocks]) / obs.noise["survey"])

    def rms(xs: list[np.ndarray]) -> float:
        return float(np.sqrt(np.mean(np.concatenate(xs) ** 2))) if xs else 0.0

    return {"census": rms(cz), "survey": rms(sz), "census_max_relative": float(max(rel)) if rel else 0.0}


def bootstrap(f: Fit, obs: Observations, geo: Geography, history: History, design: Design, n: int,
              rng: np.random.Generator, should_stop: Callable[[], None] = lambda: None
              ) -> list[tuple[Fit, Observations]]:
    """Bootstrap paramétrique : observations re-tirées du modèle ajusté, ré-estimation à chaque tirage."""
    end = max(design.census_years)
    base = predict(f, obs, geo, history, end)
    out = []
    for _ in range(n):
        should_stop()
        o = observe(base, geo, design, rng)
        out.append((fit(o, geo, history, f.model, should_stop=should_stop), o))
    return out


# --- indicateurs (agrégés : aucune sortie par cellule) --------------------------------------------

def indicators(traj: Trajectory, year: int, geo: Geography, east: np.ndarray, groups: list[str]) -> dict[str, Any]:
    """Indicateurs de 2025 autour d'une ligne de référence (la frontière factuelle).

    - part des liens fonctionnels qui traversent la ligne ;
    - part de la population à l'est de la ligne ;
    - identification moyenne à l'entité d'appartenance, de chaque côté ;
    - parts de groupes de chaque côté (CONTROLLED : jamais exportées publiquement).
    """
    p = traj.population[year]
    tot = p.sum(axis=1)
    w = geo.k_tie * tot[:, None] * tot[None, :]
    cross = east[:, None] != east[None, :]
    s = traj.identity[year]
    out: dict[str, Any] = {
        "cross_line_ties": float(w[cross].sum() / w.sum()),
        "population_share_east": float(tot[east].sum() / tot.sum()),
        "identity_east": float((s * tot)[east].sum() / tot[east].sum()),
        "identity_west": float((s * tot)[~east].sum() / tot[~east].sum()),
    }
    for side, m in (("east", east), ("west", ~east)):
        g = p[m].sum(axis=0)
        for k, name in enumerate(groups):
            out[f"group_share_{name}_{side}"] = float(g[k] / g.sum())
    return out
