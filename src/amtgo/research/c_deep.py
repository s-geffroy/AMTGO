"""Map-C-Deep sur monde historique synthétique : génération, validation, ensemble, contre-factuel.

La vérité du monde (θ vrai, état initial vrai) ne sert qu'à **générer** l'histoire
observée et à **calibrer** le contre-factuel après coup. L'estimation, la
validation et la simulation contre-factuelle ne lisent que les observations.

Gate H (historique), par modèle structurel :
- temporal holdout : moyenne quadratique des résidus standardisés hors échantillon ≤ tolérance ;
- leave-region-out : idem, blocs du nord retenus. Le découpage est orthogonal à la
  partition : les deux côtés de la frontière restent représentés ;
- placebo : une frontière fictive (jamais existé) ne doit pas recevoir d'effet,
  |β_placebo| ≤ z·se.

Les modèles qui passent forment l'ensemble ; l'incertitude de forme structurelle
n'est pas résorbée en retenant une seule forme. Le Gate H est nécessaire, pas suffisant :
une forme fausse le passe et manque la vérité contre-factuelle (red-team). Moins de
``min_structural_forms`` formes validées : NOT_IDENTIFIABLE, pas de contre-factuel.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from amtgo.manifests.c_deep import CDeepRequest, InstitutionalEpoch
from amtgo.research import historical_scm as h

INDICATORS = ("cross_line_ties", "population_share_east", "identity_east", "identity_west")


def world_geography(req: CDeepRequest) -> h.Geography:
    w, k = req.world, req.world.kernels
    bx, by = req.observation.block
    return h.geography(w.nx, w.ny, w.spacing_km, (bx, by), k.migration_km, k.capital_km, k.ties_km)


def _cells(req: CDeepRequest, geo: h.Geography) -> tuple[np.ndarray, np.ndarray]:
    x, y = geo.xy[:, 0] / req.world.spacing_km, geo.xy[:, 1] / req.world.spacing_km
    return x, y


def history(req: CDeepRequest, geo: h.Geography, epochs: tuple[InstitutionalEpoch, ...]) -> h.History:
    x, _ = _cells(req, geo)
    nx = req.world.nx
    periods = []
    for e in epochs:
        assign = np.zeros(geo.n, dtype=int) if e.border_x is None else (x >= e.border_x).astype(int)
        periods.append(h.Period(e.year, assign, tuple(int(cy * nx + cx) for cx, cy in e.capitals)))
    return h.History(tuple(periods))


def true_initial_state(req: CDeepRequest, geo: h.Geography) -> tuple[np.ndarray, np.ndarray]:
    """État initial vrai du monde synthétique (densité de fond + bourgs ; part du second groupe)."""
    w = req.world
    x, y = _cells(req, geo)
    sp = w.spacing_km
    dens = np.full(geo.n, w.background)
    for t in w.towns:
        dens += t.peak * np.exp(-((x - t.x) ** 2 + (y - t.y) ** 2) * sp * sp / (2 * t.scale_km ** 2))
    g = w.second_group
    share = g.max_share * np.exp(-((x - g.x) ** 2 + (y - g.y) ** 2) * sp * sp / (2 * g.scale_km ** 2))
    return np.column_stack([dens * (1 - share), dens * share]), np.full(geo.n, w.identity_initial)


def design(req: CDeepRequest) -> h.Design:
    o = req.observation
    return h.Design(o.census_years, o.share_years, o.survey_years, dict(o.noise))


def generate(req: CDeepRequest) -> tuple[h.Observations, dict[str, Any]]:
    """Histoire factuelle vraie, ses observations bruitées, et la vérité contre-factuelle (calibration)."""
    geo = world_geography(req)
    p0, s0 = true_initial_state(req, geo)
    w, hs = req.world, req.history
    fact = h.simulate(w.truth, geo, history(req, geo, hs.factual), p0, s0, w.growth_per_decade, hs.start, hs.end)
    cf = h.simulate(w.truth, geo, history(req, geo, hs.counterfactual), p0, s0, w.growth_per_decade, hs.start,
                    hs.end)
    obs = h.observe(fact, geo, design(req), np.random.default_rng(w.seed))
    east = east_mask(req, geo)
    groups = list(w.groups)
    truth = {"factual": h.indicators(fact, hs.end, geo, east, groups),
             "counterfactual": h.indicators(cf, hs.end, geo, east, groups), "theta": dict(w.truth)}
    return obs, truth


def east_mask(req: CDeepRequest, geo: h.Geography) -> np.ndarray:
    x, _ = _cells(req, geo)
    return x >= req.reference_line_x


def north_blocks(req: CDeepRequest, geo: h.Geography) -> np.ndarray:
    _, y = _cells(req, geo)
    north = np.unique(geo.blocks[y >= req.world.ny / 2])
    return np.array(sorted(set(north.tolist())))


def estimate(req: CDeepRequest, obs: h.Observations, model: h.Model,
             should_stop: Any = lambda: None) -> dict[str, Any]:
    """Estimation complète, holdout temporel, leave-region-out et placebo d'un modèle structurel."""
    geo = world_geography(req)
    fact = history(req, geo, req.history.factual)
    v = req.validation
    full = h.fit(obs, geo, fact, model, should_stop=should_stop)
    all_years = set(obs.census) | set(obs.shares) | set(obs.survey)
    early = {y for y in all_years if y < v.holdout_from}
    late = {y for y in all_years if y >= v.holdout_from}
    all_blocks = np.arange(geo.n_blocks)
    ho = h.fit(obs, geo, fact, model, years=early, should_stop=should_stop)
    ho_err = h.prediction_error(h.predict(ho, obs, geo, fact, req.history.end), obs, geo, late, all_blocks)
    north = north_blocks(req, geo)
    south = np.array(sorted(set(all_blocks.tolist()) - set(north.tolist())))
    lro = h.fit(obs, geo, fact, model, blocks=south, should_stop=should_stop)
    lro_err = h.prediction_error(h.predict(lro, obs, geo, fact, req.history.end), obs, geo, all_years - {obs.start},
                                 north)
    _, y = _cells(req, geo)
    side = (y >= v.placebo.border_y).astype(int)
    pl = h.fit(obs, geo, fact, model, placebo=(side, v.placebo.year), should_stop=should_stop)
    tol = {"census": v.tolerance_rms_z, "survey": v.tolerance_rms_z}  # résidus standardisés : sans unité
    bp, se = pl.placebo["beta_placebo"], pl.placebo["se"]
    checks = {
        "temporal_holdout": {"error": ho_err, "tolerance": tol,
                             "passed": all(ho_err[k] <= tol[k] for k in tol)},
        "leave_region_out": {"error": lro_err, "tolerance": tol, "held_out_blocks": north.tolist(),
                             "passed": all(lro_err[k] <= tol[k] for k in tol)},
        "placebo": {"beta_placebo": bp, "se": se, "z": v.placebo_z,
                    "passed": se is not None and bp is not None and abs(bp) <= v.placebo_z * se}}
    return {"model": model.value, "theta": full.theta, "se": full.se, "growth": full.growth, "cost": full.cost,
            "n_obs": full.n_obs, "checks": checks, "gate_h": all(c["passed"] for c in checks.values())}


def ensemble_draws(req: CDeepRequest, obs: h.Observations, est: dict[str, Any],
                   should_stop: Any = lambda: None) -> list[dict[str, float]]:
    """θ par bootstrap paramétrique (bruit d'observation déclaré), pour un modèle validé."""
    geo = world_geography(req)
    fact = history(req, geo, req.history.factual)
    f = h.Fit(h.Model(est["model"]), est["theta"], est["se"], est["growth"], est["cost"], est["n_obs"])
    rng = np.random.default_rng([req.validation.seed, list(h.Model).index(f.model)])
    draws = h.bootstrap(f, obs, geo, fact, design(req), req.validation.bootstrap, rng, should_stop)
    return [{**b.theta, "growth": b.growth} for b, _ in draws]


def counterfactual(req: CDeepRequest, obs: h.Observations, draws: dict[str, list[dict[str, float]]],
                   truth: dict[str, Any] | None) -> dict[str, Any]:
    """X_2025 factuel reconstruit et contre-factuel, par tirage de l'ensemble ; intervalles ; calibration."""
    geo = world_geography(req)
    hs = req.history
    fact, cf = history(req, geo, hs.factual), history(req, geo, hs.counterfactual)
    p0, s0 = h.initial_state(obs, geo)
    east, groups = east_mask(req, geo), list(req.world.groups)
    rows: dict[str, list[dict[str, float]]] = {"factual": [], "counterfactual": [], "delta": []}
    for _model, ths in sorted(draws.items()):
        for th in ths:
            theta = {k: th[k] for k in h.PARAMS}
            a = h.indicators(h.simulate(theta, geo, fact, p0, s0, th["growth"], hs.start, hs.end), hs.end, geo,
                             east, groups)
            b = h.indicators(h.simulate(theta, geo, cf, p0, s0, th["growth"], hs.start, hs.end), hs.end, geo,
                             east, groups)
            rows["factual"].append(a)
            rows["counterfactual"].append(b)
            rows["delta"].append({k: b[k] - a[k] for k in a})
    q = (1 - req.validation.interval_level) / 2
    out: dict[str, Any] = {}
    for kind, rs in rows.items():
        out[kind] = {k: {"median": float(np.median([r[k] for r in rs])),
                         "lo": float(np.quantile([r[k] for r in rs], q)),
                         "hi": float(np.quantile([r[k] for r in rs], 1 - q))} for k in rs[0]}
    out["n_draws"] = len(rows["factual"])
    if truth is not None:
        t_delta = {k: truth["counterfactual"][k] - truth["factual"][k] for k in truth["factual"]}
        out["calibration"] = {
            k: {"truth_counterfactual": truth["counterfactual"][k], "truth_delta": t_delta[k],
                "counterfactual_covered": out["counterfactual"][k]["lo"] <= truth["counterfactual"][k]
                <= out["counterfactual"][k]["hi"],
                "delta_covered": out["delta"][k]["lo"] <= t_delta[k] <= out["delta"][k]["hi"],
                "sign_recovered": bool(np.sign(out["delta"][k]["median"]) == np.sign(t_delta[k]))}
            for k in INDICATORS}
    return out
