"""Fusion linéaire-gaussienne (ADR-0013) : p(Z | D) ∝ p(Z) Π_o p(o | Z, Q_o).

Prior diagonal Z ~ N(μ₀, diag(v₀)), observations y = H Z + ε, ε ~ N(0, R).
Avec M observations ≪ N cellules, tout passe par la matrice d'innovation
S = H V₀ Hᵀ + R (M × M) :

    μ   = μ₀ + K S⁻¹ (y − H μ₀),        K = V₀ Hᵀ
    var = v₀ − diag(K S⁻¹ Kᵀ)

Les tirages postérieurs suivent la règle de Matheron, exacte en gaussien et sans
jamais former la covariance N × N :

    z = z₀ + K S⁻¹ (y − H z₀ − ε),  z₀ ~ N(μ₀, V₀), ε ~ N(0, R)

Les tirages conservent les corrélations a posteriori : une somme sur une région
s'obtient en sommant les tirages, sans hypothèse d'indépendance.

Une cellule sans observation garde son prior : le modèle ne prétend rien savoir
de plus (ratio d'information nul, classe D).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import sparse

from amtgo.errors import InsufficientEvidence
from amtgo.measurement.likelihoods import DesignRow


@dataclass(frozen=True)
class GaussianPrior:
    mean: np.ndarray  # (N,)
    var: np.ndarray  # (N,)


@dataclass(frozen=True)
class Posterior:
    mean: np.ndarray  # (N,)
    var: np.ndarray  # (N,)
    samples: np.ndarray  # (n_samples, N)
    prior: GaussianPrior
    n_observations: int
    # (var_post, var_prior) dans l'espace du prior quand il diffère de Z (log-normal).
    info_var: tuple[np.ndarray, np.ndarray] | None = None

    @property
    def information_ratio(self) -> np.ndarray:
        """1 − var_post / var_prior ∈ [0, 1] : part de l'incertitude a priori levée par les données.

        Calculé dans l'espace où le prior est posé (Z pour le gaussien, log ρ pour le log-normal).
        """
        post_var, prior_var = self.info_var if self.info_var is not None else (self.var, self.prior.var)
        return np.asarray(np.clip(1.0 - post_var / prior_var, 0.0, 1.0))

    @property
    def negative_fraction(self) -> np.ndarray:
        """Part des tirages négatifs par cellule : diagnostic de mauvaise spécification gaussienne."""
        return np.asarray((self.samples < 0).mean(axis=0))


def _sparse_design(rows: list[DesignRow], n: int) -> sparse.csr_matrix:
    data = np.concatenate([row.weights for row in rows]) if rows else np.zeros(0)
    cols = np.concatenate([row.cells for row in rows]) if rows else np.zeros(0, dtype=int)
    ptr = np.concatenate([[0], np.cumsum([len(row.cells) for row in rows])])
    return sparse.csr_matrix((data, cols, ptr), shape=(len(rows), n))


def _design_matrix(rows: list[DesignRow], n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h = np.zeros((len(rows), n))
    for i, row in enumerate(rows):
        h[i, row.cells] = row.weights
    y = np.array([r.y for r in rows])
    r = np.array([r.r for r in rows])
    return h, y, r


def fuse(prior: GaussianPrior, rows: list[DesignRow], n_samples: int, seed: int) -> Posterior:
    n = len(prior.mean)
    if np.any(prior.var <= 0):
        raise InsufficientEvidence("variance a priori non positive")
    rng = np.random.default_rng(seed)
    z0 = prior.mean + rng.standard_normal((n_samples, n)) * np.sqrt(prior.var)
    if not rows:
        return Posterior(prior.mean.copy(), prior.var.copy(), z0, prior, 0)

    h, y, r = _design_matrix(rows, n)
    k = prior.var[:, None] * h.T  # (N, M)
    s = h @ k + np.diag(r)  # (M, M)
    chol = np.linalg.cholesky(s)

    def solve(b: np.ndarray) -> np.ndarray:
        return np.linalg.solve(chol.T, np.linalg.solve(chol, b))

    mean = prior.mean + k @ solve(y - h @ prior.mean)
    s_inv_kt = solve(k.T)  # (M, N)
    var = np.maximum(prior.var - np.einsum("nm,mn->n", k, s_inv_kt), 0.0)

    eps = rng.standard_normal((n_samples, len(rows))) * np.sqrt(r)
    innov = y[None, :] - z0 @ h.T - eps  # (S, M)
    samples = z0 + solve(innov.T).T @ k.T
    return Posterior(mean, var, samples, prior, len(rows))


def predictive(post: Posterior, rows: list[DesignRow]) -> tuple[np.ndarray, np.ndarray]:
    """Moyenne et variance prédictives de nouvelles observations (posterior predictive)."""
    if not rows:
        return np.array([]), np.array([])
    h, _, r = _design_matrix(rows, len(post.mean))
    pred = post.samples @ h.T  # (S, M)
    return pred.mean(axis=0), pred.var(axis=0, ddof=1) + r


# --- Prior log-normal : positivité par construction (ADR-0013, révision M3) -------

# Critères numériques de convergence de Gauss-Newton (pas des paramètres scientifiques).
GN_MAX_ITER = 100
GN_TOL = 1e-6
GN_ARMIJO = 1e-4
GN_MAX_HALVINGS = 30


@dataclass(frozen=True)
class LogNormalPrior:
    """x_i = log ρ_i ~ N(μ_i, σ_i²) ; Z_i = A_i e^{x_i}.

    Avec ``mixing`` (M_x, N × K) et ``z_var`` (K) : x = μ + M_x z, z ~ N(0, diag(z_var)),
    des facteurs latents indépendants dont certains sont partagés entre cellules
    (corrélation a priori). ``log_var`` reste la variance marginale de chaque x_i.
    Sans ``mixing``, M_x est l'identité et z_var = log_var (prior indépendant).
    """

    log_mean: np.ndarray  # (N,)
    log_var: np.ndarray  # (N,)
    area: np.ndarray  # (N,) km²
    mixing: sparse.csr_matrix | None = None
    z_var: np.ndarray | None = None

    def factors(self) -> tuple[sparse.csr_matrix, np.ndarray]:
        if self.mixing is None or self.z_var is None:
            return sparse.identity(len(self.log_mean), format="csr"), self.log_var
        return self.mixing, self.z_var


def sample_prior(prior: LogNormalPrior, n_samples: int, seed: int) -> np.ndarray:
    """(S, N) tirages a priori de Z, corrélations comprises."""
    mx, vz = prior.factors()
    z0 = np.random.default_rng(seed).standard_normal((n_samples, len(vz))) * np.sqrt(vz)
    return np.asarray(prior.area * np.exp(prior.log_mean + (mx @ z0.T).T))


@dataclass(frozen=True)
class LaplaceInfo:
    iterations: int
    converged: bool
    max_step: float


def fuse_lognormal(prior: LogNormalPrior, rows: list[DesignRow], n_samples: int, seed: int
                   ) -> tuple[Posterior, LaplaceInfo]:
    """MAP par Gauss-Newton puis approximation de Laplace, dans l'espace des facteurs latents.

    Modèle : y = W ρ + ε avec W_oj = h_oj A_j (h_oj est le coefficient de Z_j), et
    x = log ρ = μ + M_x z, z ~ N(0, diag(v_z)). On linéarise f(z) = W e^{μ + M_x z}
    autour de l'itéré courant ; à la convergence, la postérieure de z est gaussienne
    (Laplace) et les tirages suivent la règle de Matheron appliquée au modèle
    linéarisé au mode. Z = A e^x est positif. Pour un prior indépendant, M_x = I.
    """
    n = len(prior.log_mean)
    mx, vz = prior.factors()
    rng = np.random.default_rng(seed)
    z0_samples = rng.standard_normal((n_samples, len(vz))) * np.sqrt(vz)
    x0_samples = prior.log_mean + (mx @ z0_samples.T).T
    prior_z = GaussianPrior(prior.area * np.exp(prior.log_mean + prior.log_var / 2),
                            (prior.area**2) * (np.exp(prior.log_var) - 1) * np.exp(2 * prior.log_mean + prior.log_var))
    if not rows:
        z = prior.area * np.exp(x0_samples)
        return (Posterior(z.mean(axis=0), z.var(axis=0, ddof=1), z, prior_z, 0),
                LaplaceInfo(0, True, 0.0))

    w = _sparse_design(rows, n).multiply(prior.area[None, :]).tocsr()  # W_oj = h_oj A_j
    y = np.array([row.y for row in rows])
    r = np.array([row.r for row in rows])
    mu = prior.log_mean

    def objective(zv: np.ndarray) -> float:
        res = y - w @ np.exp(mu + mx @ zv)
        return float(0.5 * np.sum(res**2 / r) + 0.5 * np.sum(zv**2 / vz))

    def jacobian(zv: np.ndarray) -> tuple[np.ndarray, sparse.csr_matrix]:
        rho = np.exp(mu + mx @ zv)
        return rho, (w.multiply(rho[None, :]) @ mx).tocsr()  # jacobienne de f en z

    def innovation_matrix(j: sparse.csr_matrix) -> np.ndarray:
        # S = J V_z Jᵀ + R, formé en creux : chaque EA ne touche qu'une dizaine de cellules.
        return np.asarray((j.multiply(vz[None, :]) @ j.T).toarray()) + np.diag(r)

    zc = np.zeros(len(vz))
    fx = objective(zc)
    converged, step, it = False, np.inf, 0
    for it in range(1, GN_MAX_ITER + 1):  # noqa: B007
        rho, j = jacobian(zc)
        s = innovation_matrix(j)
        pseudo = y - w @ rho + j @ zc
        d = vz * (j.T @ np.linalg.solve(s, pseudo)) - zc  # direction de Gauss-Newton
        # Gradient de l'objectif MAP, pour la condition d'Armijo.
        grad = -(j.T @ ((y - w @ rho) / r)) + zc / vz
        slope = float(grad @ d)
        t = 1.0
        for _ in range(GN_MAX_HALVINGS):
            cand = zc + t * d
            fc = objective(cand)
            if np.isfinite(fc) and fc <= fx + GN_ARMIJO * t * slope:
                break
            t /= 2.0
        else:
            break  # aucun pas acceptable : non convergé, rapporté comme tel
        step = float(np.max(np.abs(t * d)))
        zc, fx = cand, fc
        if step < GN_TOL:
            converged = True
            break

    rho, j = jacobian(zc)
    s = innovation_matrix(j)
    chol = np.linalg.cholesky(s)

    def solve(b: np.ndarray) -> np.ndarray:
        return np.linalg.solve(chol.T, np.linalg.solve(chol, b))

    jd = np.asarray(j.toarray())  # (M, K), dense : M × K reste modeste
    # Variance a posteriori de x_i : diag(M_x V_z M_xᵀ) − diag(B S⁻¹ Bᵀ), B = M_x V_z Jᵀ (N × M).
    b = np.asarray((mx.multiply(vz[None, :]) @ j.T).toarray())
    var_x = np.maximum(prior.log_var - np.einsum("nm,mn->n", b, solve(b.T)), 1e-300)
    # Matheron au mode : pseudo-observation ỹ = y − f(ẑ) + J ẑ.
    y_tilde = y - w @ rho + j @ zc
    eps = rng.standard_normal((n_samples, len(rows))) * np.sqrt(r)
    innov = y_tilde[None, :] - (j @ z0_samples.T).T - eps  # (S, M)
    z_samples = z0_samples + (solve(innov.T).T @ jd) * vz[None, :]
    x_samples = mu + (mx @ z_samples.T).T
    z = prior.area * np.exp(x_samples)
    # Le ratio d'information est défini dans l'espace où le prior est posé (log).
    post = Posterior(z.mean(axis=0), z.var(axis=0, ddof=1), z, prior_z, len(rows),
                     info_var=(var_x, prior.log_var))
    return post, LaplaceInfo(it, converged, step)


# --- Marges administratives : recalage exact des tirages (désagrégation) -----------

# Tolérance et plafond numériques du recalage (pas des paramètres scientifiques).
RAKE_TOL = 1e-9
RAKE_MAX_ITER = 500


def rake_to_margins(post: Posterior, margins: list[DesignRow], seed: int,
                    prior_log_var: np.ndarray) -> Posterior:
    """Recale chaque tirage sur des totaux de polygones disjoints, eux-mêmes tirés selon leur bruit.

    Itération de point fixe : chaque cellule est multipliée par la moyenne, pondérée
    par sa part de surface, des facteurs T_d / (total courant) des polygones qu'elle
    touche (la part hors polygone garde un facteur 1). Les marges doivent être
    disjointes. Le ratio d'information devient empirique, dans l'espace log.
    """
    n = len(post.mean)
    h, y, r = _design_matrix(margins, n)
    covered = h.sum(axis=0)
    if np.any(covered > 1.0 + 1e-6):
        raise InsufficientEvidence("marges non disjointes : le recalage exact n'est pas défini")
    rng = np.random.default_rng([seed, 99])
    t = np.maximum(y[None, :] + rng.standard_normal((len(post.samples), len(margins))) * np.sqrt(r), 0.0)
    z = post.samples.copy()
    # Point fixe (IPF à appartenance fractionnaire) : une cellule à cheval sur une marge
    # est mise à l'échelle en entier, pour rester cohérente avec l'hypothèse d'homogénéité.
    for _ in range(RAKE_MAX_ITER):
        current = z @ h.T  # (S, D)
        scale = np.divide(t, current, out=np.ones_like(t), where=current > 0)
        z = z * ((1.0 - covered)[None, :] + scale @ h)
        err = np.abs(z @ h.T - t) / np.maximum(t, 1.0)
        if float(err.max()) < RAKE_TOL:
            break
    else:
        raise InsufficientEvidence("recalage sur les marges non convergé")
    log_var_post = np.log(np.maximum(z, 1e-300)).var(axis=0, ddof=1)
    return Posterior(z.mean(axis=0), z.var(axis=0, ddof=1), z, post.prior,
                     post.n_observations + len(margins), info_var=(log_var_post, prior_log_var))
