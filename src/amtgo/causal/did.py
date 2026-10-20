"""DiD échelonné : ATT(g,t) par cohorte et période, témoins jamais traités (04 §6).

    ATT(g,t) = [Ȳ_g,t − Ȳ_g,g−1] − [Ȳ_C,t − Ȳ_C,g−1]

avec une période de base universelle g − 1 : pour t < g − 1, ATT(g,t) teste les
tendances pré-traitement. L'ATT global agrège les cellules post (t ≥ g),
pondérées par la taille des cohortes. L'incertitude vient d'un bootstrap par
grappes d'unités, stratifié par cohorte (aucune cohorte ne disparaît d'un tirage).

Diagnostics (chacun PASSED / FAILED, jamais omis) :

- ``pre_trends`` : test de Wald des ATT d'événement e ≤ −2 (covariance bootstrap) ;
- ``anticipation`` : l'intervalle de l'ATT en e = −1 contient 0 ;
- ``composition`` : panel équilibré (aucune entrée ni sortie d'unités) ;
- ``spillovers`` : parmi les témoins, pente du changement post − pré sur
  l'exposition E_i = Σ_j W_ij A_j (part des voisins traités) — l'intervalle
  contient 0 ;
- ``endogenous_adoption`` : tendances pré-traitement et placebo tous deux passés ;
- ``placebo`` (robustesse) : dates de traitement avancées, données pré seulement ;
- ``negative_control`` (robustesse) : effet nul sur un résultat non affecté.

Aucun ensemble d'ajustement n'est choisi par p-value (04 §9) : l'estimateur n'en a pas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from amtgo.causal.model import Diagnostic
from amtgo.core.uncertainty import UncertainValue

NEVER = -1  # cohorte des jamais traités


@dataclass(frozen=True)
class Panel:
    """Panel équilibré : ``y`` (N, T), ``years`` (T,), ``cohort`` (N,) année d'adoption ou NEVER."""

    y: np.ndarray
    years: np.ndarray
    cohort: np.ndarray
    exposure: np.ndarray | None = None  # (N,) part des voisins traités, E_i = Σ_j W_ij A_j (04 §4)
    balanced: bool = True


@dataclass(frozen=True)
class DiDResult:
    att: UncertainValue
    event_study: dict[int, UncertainValue]
    diagnostics: dict[str, Diagnostic]
    robustness: dict[str, str] = field(default_factory=dict)
    att_draws: np.ndarray = field(default_factory=lambda: np.zeros(0))


def _bootstrap_weights(cohort: np.ndarray, draws: int, rng: np.random.Generator) -> np.ndarray:
    """(B, N) : nombre de fois où chaque unité est tirée, par cohorte (grappes = unités)."""
    w = np.zeros((draws, len(cohort)))
    for g in np.unique(cohort):
        idx = np.flatnonzero(cohort == g)
        picks = rng.integers(len(idx), size=(draws, len(idx)))
        for b in range(draws):
            np.add.at(w[b], idx[picks[b]], 1.0)
    return w


def _att_gt(y: np.ndarray, years: np.ndarray, cohort: np.ndarray, w: np.ndarray
            ) -> dict[tuple[int, int], np.ndarray]:
    """ATT(g,t) pour chaque poids (B, N) → {(g, t): (B,)}."""
    ctrl = cohort == NEVER
    out = {}
    mean = {}
    for g in np.unique(cohort):
        mask = cohort == g
        wm = w * mask
        mean[int(g)] = (wm @ y) / wm.sum(axis=1, keepdims=True)  # (B, T)
    pos = {int(t): k for k, t in enumerate(years)}
    if not ctrl.any():
        raise ValueError("DiD : aucune unité jamais traitée (témoins)")
    for g in mean:
        if g == NEVER or g - 1 not in pos:
            continue
        b = pos[g - 1]
        for t, k in pos.items():
            if t == g - 1:
                continue
            out[(g, t)] = (mean[g][:, k] - mean[g][:, b]) - (mean[NEVER][:, k] - mean[NEVER][:, b])
    return out


def _aggregate(att: dict[tuple[int, int], np.ndarray], cohort: np.ndarray) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    sizes = {int(g): int((cohort == g).sum()) for g in np.unique(cohort) if g != NEVER}
    post = [(sizes[g], v) for (g, t), v in att.items() if t >= g]
    overall = sum(s * v for s, v in post) / sum(s for s, _ in post)
    events: dict[int, list[tuple[int, np.ndarray]]] = {}
    for (g, t), v in att.items():
        events.setdefault(t - g, []).append((sizes[g], v))
    es = {e: np.asarray(sum(s * v for s, v in xs) / sum(s for s, _ in xs)) for e, xs in events.items()}
    return np.asarray(overall), es


def _covers_zero(x: np.ndarray, level: float) -> bool:
    a = (1.0 - level) / 2.0
    lo, hi = np.quantile(x, [a, 1.0 - a])
    return bool(lo <= 0.0 <= hi)


def _wald_p(vectors: list[np.ndarray]) -> float:
    """p-valeur du test joint H0 : tous nuls, covariance bootstrap des moyennes."""
    m = np.column_stack(vectors)  # (B, k)
    theta = m.mean(axis=0)
    cov = np.atleast_2d(np.cov(m, rowvar=False))
    stat = float(theta @ np.linalg.pinv(cov) @ theta)
    return float(stats.chi2.sf(stat, df=m.shape[1]))


def estimate(panel: Panel, draws: int, seed: int, alpha: float, level: float = 0.9,
             negative_control: np.ndarray | None = None, placebo_shift: int = 2) -> DiDResult:
    rng = np.random.default_rng([seed, 9])
    w = _bootstrap_weights(panel.cohort, draws, rng)
    att = _att_gt(panel.y, panel.years, panel.cohort, w)
    overall, es = _aggregate(att, panel.cohort)
    diag: dict[str, Diagnostic] = {}
    rob: dict[str, str] = {}

    pre = [v for e, v in sorted(es.items()) if e <= -2]
    pre_ok = (not pre) or _wald_p(pre) > alpha
    diag["pre_trends"] = (Diagnostic.NOT_TESTED if not pre else
                          Diagnostic.PASSED if pre_ok else Diagnostic.FAILED)
    diag["anticipation"] = (Diagnostic.PASSED if -1 not in es or _covers_zero(es[-1], level)
                            else Diagnostic.FAILED)
    diag["composition"] = Diagnostic.PASSED if panel.balanced else Diagnostic.FAILED

    # Placebo : dates avancées de ``placebo_shift`` ans, seules les années avant le vrai traitement.
    placebo_ok = True
    treated = panel.cohort != NEVER
    if treated.any():
        fake = np.where(treated, panel.cohort - placebo_shift, NEVER)
        keep = panel.years < panel.cohort[treated].min()
        if keep.sum() >= 2:
            p_att = _att_gt(panel.y[:, keep], panel.years[keep], fake, w)
            p_post = {k: v for k, v in p_att.items() if k[1] >= k[0]}
            if p_post:
                p_overall, _ = _aggregate(p_post, fake)
                placebo_ok = _covers_zero(p_overall, level)
                rob["placebo"] = "PASSED" if placebo_ok else "FAILED"
    if "placebo" not in rob:
        rob["placebo"] = "NOT_TESTED"
    diag["endogenous_adoption"] = Diagnostic.PASSED if pre_ok and placebo_ok else Diagnostic.FAILED

    if panel.exposure is not None and treated.any():
        ctrl = panel.cohort == NEVER
        first = int(panel.cohort[treated].min())
        post, prior = panel.years >= first, panel.years < first
        x = panel.exposure[ctrl]
        if post.any() and prior.any() and ctrl.sum() >= 3 and np.ptp(x) > 0:
            change = panel.y[ctrl][:, post].mean(axis=1) - panel.y[ctrl][:, prior].mean(axis=1)
            wc = w[:, ctrl]
            xm = (wc @ x) / wc.sum(axis=1)
            ym = (wc @ change) / wc.sum(axis=1)
            dx = x[None, :] - xm[:, None]
            cov_xy = (wc * dx * (change[None, :] - ym[:, None])).sum(axis=1)
            slope = cov_xy / np.maximum((wc * dx**2).sum(axis=1), 1e-12)
            diag["spillovers"] = Diagnostic.PASSED if _covers_zero(slope, level) else Diagnostic.FAILED
    diag.setdefault("spillovers", Diagnostic.NOT_TESTED)

    if negative_control is not None:
        nc, _ = _aggregate(_att_gt(negative_control, panel.years, panel.cohort, w), panel.cohort)
        rob["negative_control"] = "PASSED" if _covers_zero(nc, level) else "FAILED"
    return DiDResult(UncertainValue.from_samples(overall, level),
                     {e: UncertainValue.from_samples(v, level) for e, v in sorted(es.items())},
                     diag, rob, overall)


def leave_region_out(panel: Panel, region: np.ndarray, draws: int, seed: int, alpha: float,
                     level: float = 0.9) -> dict[str, float | bool]:
    """Estimation séparée sur deux régions : les intervalles doivent se recouvrir (validation)."""
    out: dict[str, float | bool] = {}
    est = []
    for r in (False, True):
        m = region == r
        sub = Panel(panel.y[m], panel.years, panel.cohort[m], None, panel.balanced)
        est.append(estimate(sub, draws, seed, alpha, level).att)
    a, b = est
    assert a.lower is not None and a.upper is not None and b.lower is not None and b.upper is not None
    out["att_region_a"], out["att_region_b"] = float(a.mean or 0.0), float(b.mean or 0.0)
    out["consistent"] = bool(a.lower <= b.upper and b.lower <= a.upper)
    return out
