"""SCM historique de Map-C-Deep : mécanismes, identification, validation, et sa limite (red-team)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from amtgo.config.loader import load_model
from amtgo.manifests.c_deep import CDeepRequest
from amtgo.research import c_deep as cd
from amtgo.research import historical_scm as h

CONFIG = Path(__file__).resolve().parents[2] / "configs" / "research" / "c_deep_synthetic.yaml"


@pytest.fixture(scope="module")
def req() -> CDeepRequest:
    r = load_model(CDeepRequest, CONFIG)
    return r.model_copy(update={"validation": r.validation.model_copy(update={"bootstrap": 12})})


@pytest.fixture(scope="module")
def world(req: CDeepRequest) -> tuple[h.Geography, h.History, h.History, np.ndarray, np.ndarray]:
    geo = cd.world_geography(req)
    p0, s0 = cd.true_initial_state(req, geo)
    return (geo, cd.history(req, geo, req.history.factual), cd.history(req, geo, req.history.counterfactual),
            p0, s0)


def test_migration_conserves_population_and_border_brakes_it(req: CDeepRequest, world: Any) -> None:
    geo, fact, cf, p0, s0 = world
    th = dict(req.world.truth)
    t = h.simulate(th, geo, fact, p0, s0, 0.0, 1885, 2025)
    assert t.population[2025].sum() == pytest.approx(p0.sum())  # la migration ne crée ni ne détruit personne
    east = cd.east_mask(req, geo)
    free = h.simulate({**th, "beta": 0.0}, geo, fact, p0, s0, 0.0, 1885, 2025)
    # Le groupe b vit surtout à l'est de la ligne : avec friction, moins de ses membres gagnent l'ouest.
    assert t.population[2025][:, 1][~east].sum() < free.population[2025][:, 1][~east].sum()
    # Sans partition, aucune remise à zéro de l'identification à l'est.
    c = h.simulate(th, geo, cf, p0, s0, 0.0, 1885, 2025)
    assert c.identity[1935][east].mean() > t.identity[1935][east].mean()


def test_scm_recovers_border_effect_and_placebo_is_null(req: CDeepRequest) -> None:
    obs, truth = cd.generate(req)
    est = cd.estimate(req, obs, h.Model.BORDER_FRICTION)
    th, se = est["theta"], est["se"]
    assert abs(th["beta"] - truth["theta"]["beta"]) <= 3 * se["beta"]
    assert abs(th["lam"] - truth["theta"]["lam"]) <= 3 * se["lam"]
    assert est["gate_h"] and est["checks"]["placebo"]["passed"]


def test_insufficient_history_is_not_identifiable(req: CDeepRequest) -> None:
    thin = req.model_copy(update={"observation": req.observation.model_copy(
        update={"census_years": (1885, 2025), "survey_years": (1885, 2025), "share_years": (2025,)})})
    obs, _ = cd.generate(thin)
    with pytest.raises(ValueError, match="deux recensements"):  # holdout : un seul recensement avant 2005
        cd.estimate(thin, obs, h.Model.BORDER_FRICTION)


def test_ensemble_recovers_counterfactual_on_synthetic_truth(req: CDeepRequest) -> None:
    obs, truth = cd.generate(req)
    draws = {m.value: cd.ensemble_draws(req, obs, cd.estimate(req, obs, m)) for m in req.models}
    r = cd.counterfactual(req, obs, draws, truth)
    cal = r["calibration"]
    assert all(c["sign_recovered"] for c in cal.values())
    assert sum(c["delta_covered"] for c in cal.values()) >= 3
    assert r["delta"]["identity_east"]["lo"] > 0  # la partition a durablement réduit l'identification à l'est


def test_factual_validation_does_not_validate_a_counterfactual(req: CDeepRequest) -> None:
    """Red-team : une forme structurelle fausse passe le Gate H et manque pourtant la vérité contre-factuelle.

    C'est pourquoi l'ensemble doit garder au moins deux formes (``min_structural_forms``).
    """
    obs, truth = cd.generate(req)
    est = cd.estimate(req, obs, h.Model.NO_BORDER_FRICTION)
    assert est["gate_h"]
    r = cd.counterfactual(req, obs, {"no_border_friction": cd.ensemble_draws(req, obs, est)}, truth)
    assert not all(c["delta_covered"] for c in r["calibration"].values())


def test_gate_h_rejects_a_wrong_institutional_history(req: CDeepRequest) -> None:
    """Le Gate H a un pouvoir : une partition mal datée (1955 au lieu de 1925) n'explique pas l'histoire observée."""
    obs, _ = cd.generate(req)
    epochs = list(req.history.factual)
    epochs[1] = epochs[1].model_copy(update={"year": 1955})
    wrong = req.model_copy(update={"history": req.history.model_copy(update={"factual": tuple(epochs)})})
    est = cd.estimate(wrong, obs, h.Model.BORDER_FRICTION)
    assert not est["gate_h"]
