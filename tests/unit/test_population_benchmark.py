"""Benchmark du modèle spatial de population (A1, ADR-0029) : scores, validation croisée, gate.

Propriétés qualitatives (ADR-0010) :
- le CRPS sur tirages retrouve la forme analytique d'une loi normale ;
- un prédicteur calibré couvre au niveau nominal, un prédicteur surconfiant non ;
- une variante n'est jamais notée sur la moitié qui l'a fait retenir ;
- le gate refuse une sélection instable ou une couverture insuffisante ;
- toutes les variantes d'erreur gardent l'espérance du raster.
"""

from __future__ import annotations

from math import erf, exp, pi, sqrt

import numpy as np
import pytest
import yaml
from shapely.geometry import box

from amtgo.geo.mesh import BBoxExtent, MeshDefinition, MeshFamily, bbox_geometry
from amtgo.geo.ops import create_base_mesh
from amtgo.measurement import benchmark as bm
from amtgo.measurement.engine import error_mixing, raster_error_prior
from amtgo.measurement.fusion import sample_prior
from amtgo.measurement.likelihoods import MeshIndex
from amtgo.measurement.manifest import MeasurementManifest, PopulationBenchmark

EXT = BBoxExtent(bbox=(-25.0, -26.0, -22.0, -23.0))  # Atlantique Sud : aucune population réelle


def index(level: int) -> MeshIndex:
    d = MeshDefinition(mesh_id=f"bm_l{level}", family=MeshFamily.GRID_LAEA, resolution=level,
                       grid_base_km=400, extent=EXT)
    return MeshIndex(create_base_mesh(d, bbox_geometry(EXT)))


def spec(**kw: object) -> PopulationBenchmark:
    base = {"source_id": "s", "variable_id": "v", "cv_block_km": 100, "selection_score": "log_score",
            "max_coverage_shortfall": 0.1, "min_cells_per_unit": 4,
            "variants": [{"variant_id": "va", "log_sd": 1.0}, {"variant_id": "vb", "log_sd": 0.5}]}
    return PopulationBenchmark.model_validate({**base, **kw})


def test_crps_matches_normal_closed_form() -> None:
    rng = np.random.default_rng(0)
    t = rng.standard_normal((40000, 3)) * 2.0 + 10.0
    y = np.array([10.0, 12.0, 6.0])
    z = (y - 10.0) / 2.0
    pdf = np.array([exp(-x * x / 2) / sqrt(2 * pi) for x in z])
    cdf = np.array([0.5 * (1 + erf(x / sqrt(2))) for x in z])
    exact = 2.0 * (z * (2 * cdf - 1) + 2 * pdf - 1 / sqrt(pi))
    np.testing.assert_allclose(bm.crps_samples(t, y), exact, rtol=0.02)


def _units(y: np.ndarray) -> bm.Units:
    return bm.Units([f"u{i}" for i in range(len(y))], y, np.zeros(len(y)), [box(0, 0, 1, 1)] * len(y))


def test_calibrated_predictor_covers_nominally_overconfident_does_not() -> None:
    rng = np.random.default_rng(1)
    n_units, s = 4000, 400
    log_true = rng.normal(np.log(1e4), 0.6, n_units)
    y = np.exp(log_true + rng.normal(0, 0.4, n_units))
    calibrated = np.exp(log_true[None, :] + rng.normal(0, 0.4, (s, n_units)))
    overconfident = np.exp(log_true[None, :] + rng.normal(0, 0.1, (s, n_units)))
    levels = (0.5, 0.8, 0.95)
    good = bm.summarize(bm.unit_scores(calibrated, _units(y), levels, 0), np.ones(n_units, bool), levels)
    bad = bm.summarize(bm.unit_scores(overconfident, _units(y), levels, 0), np.ones(n_units, bool), levels)
    for lv in ("0.5", "0.8", "0.95"):
        assert good["coverage"][lv] == pytest.approx(float(lv), abs=0.03)
        assert bad["coverage"][lv] < float(lv) - 0.2
    assert good["log_score"] < bad["log_score"]  # le score logarithmique pénalise la surconfiance
    assert good["rms_z_log"] == pytest.approx(1.0, abs=0.1) and bad["rms_z_log"] > 2


def test_cv_folds_checkerboard_is_deterministic() -> None:
    geoms = [box(-25 + 0.5 * i, -26 + 0.5 * j, -24.9 + 0.5 * i, -25.9 + 0.5 * j) for i in range(6) for j in range(6)]
    f = bm.cv_folds(geoms, 100)
    assert set(f.tolist()) == {0, 1} and np.array_equal(f, bm.cv_folds(geoms, 100))


def _result(scores: np.ndarray, covered: np.ndarray) -> dict:
    n = len(scores)
    return {"per_unit": {"log_score": scores.tolist(), "crps_rel": scores.tolist(), "pit": [0.5] * n,
                         "z_log": [0.0] * n, "log_error": [0.0] * n,
                         **{f"covered_{lv:g}": covered.tolist() for lv in (0.5, 0.8, 0.95)}}}


def test_cross_validation_never_scores_on_selection_half() -> None:
    folds = np.array([0, 0, 1, 1])
    # « va » est préférée sur la moitié 0, « vb » sur la moitié 1 : sélection instable.
    results = {"va": _result(np.array([1.0, 1.0, 9.0, 9.0]), np.ones(4)),
               "vb": _result(np.array([5.0, 5.0, 2.0, 2.0]), np.ones(4))}
    cv = bm.cross_validate(results, folds, spec())
    assert [f["retained"] for f in cv["folds"]] == ["va", "vb"] and cv["retained"] is None
    assert cv["folds"][0]["assessment"]["log_score"] == pytest.approx(9.0)  # « va » notée sur la moitié 1
    gate = bm.gate_a1({"m": cv}, spec())
    assert not gate["passed"] and any("instable" in r for r in gate["reasons"])


def test_gate_requires_coverage_and_same_variant_on_every_mesh() -> None:
    folds = np.array([0, 0, 1, 1])
    ok = {"va": _result(np.array([1.0] * 4), np.ones(4)), "vb": _result(np.array([2.0] * 4), np.ones(4))}
    under = {"va": _result(np.array([1.0] * 4), np.zeros(4)), "vb": _result(np.array([2.0] * 4), np.ones(4))}
    cv_ok, cv_under = bm.cross_validate(ok, folds, spec()), bm.cross_validate(under, folds, spec())
    assert bm.gate_a1({"m1": cv_ok, "m2": cv_ok}, spec())["passed"]
    assert not bm.gate_a1({"m1": cv_ok, "m2": cv_under}, spec())["passed"]  # couverture nulle
    swapped = {"va": ok["vb"], "vb": ok["va"]}
    gate = bm.gate_a1({"m1": cv_ok, "m2": bm.cross_validate(swapped, folds, spec())}, spec())
    assert not gate["passed"] and any("selon le maillage" in r for r in gate["reasons"])


def test_error_mixing_components_and_marginal_variance() -> None:
    idx = index(5)
    groups = np.where(np.arange(len(idx)) % 3 == 0, -1, np.arange(len(idx)) % 4)
    mx, sizes = error_mixing(idx, True, [25.0, 100.0], groups)
    assert sizes[0] == 1 and sizes[-1] == len(idx) and mx.shape[1] == sum(sizes)
    per_row = np.asarray(mx.sum(axis=1)).ravel()
    assert np.all(per_row[groups >= 0] == 5) and np.all(per_row[groups < 0] == 4)
    p = raster_error_prior(idx, np.full(len(idx), 50.0), 0.5, 0.1, [(25.0, 0.2), (100.0, 0.3)], groups, 0.25)
    inside = 0.1**2 + 0.2**2 + 0.3**2 + 0.25**2 + 0.5**2
    np.testing.assert_allclose(p.log_var[groups >= 0], inside)
    np.testing.assert_allclose(p.log_var[groups < 0], inside - 0.25**2)


@pytest.mark.parametrize("variant", [
    {"variant_id": "indep", "log_sd": 1.0},
    {"variant_id": "multi", "log_sd": 0.5, "level_sd": 0.1, "scales": [{"block_km": 25, "sd": 0.15},
                                                                      {"block_km": 100, "sd": 0.15}]},
    {"variant_id": "unit", "log_sd": 0.5, "unit_sd": 0.3},
])
def test_every_variant_keeps_the_raster_expectation(variant: dict) -> None:
    from amtgo.measurement.manifest import ErrorModel

    idx = index(5)
    density = np.random.default_rng(5).gamma(2.0, 30.0, len(idx))
    groups = np.arange(len(idx)) % 7
    p = bm.variant_prior(idx, density, ErrorModel.model_validate(variant), groups)
    total = sample_prior(p, 20000, 9).sum(axis=1).mean()
    assert total == pytest.approx(float((density * idx.area).sum()), rel=0.03)


def test_benchmark_source_cannot_be_a_likelihood(configs_dir) -> None:  # type: ignore[no-untyped-def]
    raw = yaml.safe_load((configs_dir / "measurement" / "gha_population_2021.yaml").read_text())
    MeasurementManifest.model_validate(raw)
    leak = {**raw, "benchmark": {**raw["benchmark"], "source_id": raw["likelihoods"][0]["source_id"]}}
    with pytest.raises(ValueError, match="validation non indépendante"):
        MeasurementManifest.model_validate(leak)
    with pytest.raises(ValueError, match="dupliqués"):
        spec(variants=[{"variant_id": "va", "log_sd": 1.0}, {"variant_id": "va", "log_sd": 0.5}])
