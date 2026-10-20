"""M3 : fusion (exactitude, tirages), positivité, marges, sélection, calculabilité."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import yaml
from shapely.geometry import box

from amtgo.core.enums import ComputabilityClass, EvidenceStatus, PrivacyClass, SupportType
from amtgo.core.quality import QualityVector
from amtgo.core.uncertainty import DistributionType, UncertainValue
from amtgo.data.observations import Observation
from amtgo.errors import InsufficientEvidence
from amtgo.geo.mesh import BBoxExtent, MeshDefinition, MeshFamily
from amtgo.geo.ops import create_base_mesh
from amtgo.measurement.engine import is_holdout, select_observations
from amtgo.measurement.fields import cell_class, zone_class
from amtgo.measurement.fusion import (
    GaussianPrior,
    LogNormalPrior,
    fuse,
    fuse_lognormal,
    rake_to_margins,
)
from amtgo.measurement.likelihoods import DesignRow, MeshIndex, design_row
from amtgo.measurement.manifest import ComputabilitySpec, MeasurementManifest

Q = QualityVector(source_reliability=1, spatial_precision=1, temporal_precision=1, construct_validity=1,
                  representativeness=1, license_usability=1, privacy_usability=1)
BBOX = (-25.0, -26.0, -24.0, -25.0)


def _row(cells: list[int], w: list[float], y: float, r: float, src: str = "s") -> DesignRow:
    return DesignRow(f"o{y}", src, np.array(cells), np.array(w), y, r, 0.0)


def test_linear_fusion_matches_dense_posterior() -> None:
    rng = np.random.default_rng(0)
    n = 6
    prior = GaussianPrior(rng.uniform(1, 5, n), rng.uniform(0.5, 2, n))
    rows = [_row([0, 1], [1.0, 0.5], 4.0, 0.3), _row([2, 3, 4], [1, 1, 1], 9.0, 1.0),
            _row([5], [2.0], 3.0, 0.1)]
    post = fuse(prior, rows, n_samples=50, seed=1)
    h = np.zeros((3, n))
    for i, r in enumerate(rows):
        h[i, r.cells] = r.weights
    v0 = np.diag(prior.var)
    rmat = np.diag([r.r for r in rows])
    y = np.array([r.y for r in rows])
    cov = np.linalg.inv(np.linalg.inv(v0) + h.T @ np.linalg.inv(rmat) @ h)
    mean = cov @ (np.linalg.inv(v0) @ prior.mean + h.T @ np.linalg.inv(rmat) @ y)
    assert np.allclose(post.mean, mean, atol=1e-9)
    assert np.allclose(post.var, np.diag(cov), atol=1e-9)
    assert np.all((post.information_ratio >= 0) & (post.information_ratio <= 1))


def test_matheron_samples_have_posterior_moments() -> None:
    prior = GaussianPrior(np.array([10.0, 20.0, 5.0]), np.array([4.0, 9.0, 1.0]))
    rows = [_row([0, 1], [1, 1], 33.0, 1.0)]
    post = fuse(prior, rows, n_samples=40000, seed=3)
    assert np.allclose(post.samples.mean(axis=0), post.mean, atol=0.05)
    assert np.allclose(post.samples.var(axis=0), post.var, rtol=0.05)
    # Les corrélations a posteriori sont conservées : la somme contrainte est resserrée.
    assert post.samples[:, :2].sum(axis=1).var() < (post.var[0] + post.var[1])


def test_no_observation_keeps_prior() -> None:
    prior = GaussianPrior(np.ones(4), np.ones(4))
    post = fuse(prior, [], 30, 0)
    assert np.allclose(post.mean, 1.0) and np.allclose(post.information_ratio, 0.0)


def test_lognormal_positive_and_converged() -> None:
    n = 5
    prior = LogNormalPrior(np.full(n, np.log(20.0)), np.full(n, 1.5**2), np.full(n, 10.0))
    rows = [_row([0], [0.2], 400.0, 400.0), _row([1, 2], [0.1, 0.1], 50.0, 25.0)]
    post, info = fuse_lognormal(prior, rows, 300, 0)
    assert info.converged
    assert np.all(post.samples > 0)
    assert post.information_ratio[0] > post.information_ratio[4]  # cellule observée vs non observée
    assert post.information_ratio[4] == pytest.approx(0.0, abs=0.15)


def test_raking_hits_margins_exactly() -> None:
    n = 4
    prior = LogNormalPrior(np.zeros(n), np.ones(n), np.ones(n))
    post, _ = fuse_lognormal(prior, [], 100, 0)
    margins = [_row([0, 1], [1.0, 0.5], 100.0, 1e-6), _row([2], [1.0], 50.0, 1e-6)]
    raked = rake_to_margins(post, margins, 0, prior.log_var)
    assert np.allclose(raked.samples[:, 0] + 0.5 * raked.samples[:, 1], 100.0, rtol=1e-4)
    assert np.allclose(raked.samples[:, 2], 50.0, rtol=1e-4)
    # Cellule hors de toute marge : inchangée.
    assert np.allclose(raked.samples[:, 3], post.samples[:, 3])


def test_raking_refuses_overlapping_margins() -> None:
    prior = LogNormalPrior(np.zeros(2), np.ones(2), np.ones(2))
    post, _ = fuse_lognormal(prior, [], 20, 0)
    with pytest.raises(InsufficientEvidence):
        rake_to_margins(post, [_row([0, 1], [1, 1], 5, 1), _row([0], [1], 2, 1)], 0, prior.log_var)


@pytest.fixture(scope="module")
def grid_index() -> MeshIndex:
    d = MeshDefinition(mesh_id="gm", family=MeshFamily.GRID_LAEA, resolution=4, grid_base_km=400,
                       extent=BBoxExtent(bbox=BBOX))
    return MeshIndex(create_base_mesh(d, box(*BBOX)))


def _manifest(configs_dir: Path) -> MeasurementManifest:
    return MeasurementManifest.model_validate(
        yaml.safe_load((configs_dir / "measurement" / "population_v1.yaml").read_text()))


def _obs(kind: str, **kw: object) -> Observation:
    t = datetime(2025, 6, 1, tzinfo=UTC)
    if kind == "ea":
        base: dict[str, object] = dict(
            variable_id="population_count_ea", support_type=SupportType.UNCERTAIN_POINT,
            geometry_wkt="POINT (-24.5 -25.5)", displacement_km=5.0, value=UncertainValue.exact(40.0),
            attributes={"ea_area_km2": 2.0})
    else:
        base = dict(variable_id="population_total_admin", support_type=SupportType.ADMIN,
                    geometry_wkt=box(-24.9, -25.9, -24.1, -25.1).wkt, admin_code="d",
                    value=UncertainValue(mean=1000.0, std=30.0, distribution_type=DistributionType.NORMAL))
    base.update(id=Observation.make_id("u-" + kind, "v", str(kw), t), source_id="u-" + kind,
                valid_from=t, recorded_at=t, quality=Q, evidence_status=EvidenceStatus.DIRECT,
                sensitivity=PrivacyClass.PUBLIC)
    base.update(kw)
    return Observation(**base)  # type: ignore[arg-type]


SLUGS = {"u-ea": "synthetic_survey", "u-census": "synthetic_census"}


def test_design_rows_conserve_support(grid_index: MeshIndex, configs_dir: Path) -> None:
    m = _manifest(configs_dir)
    ea = design_row(_obs("ea"), m.likelihoods[0], grid_index)
    # Σ_j w_j A_j / a = part du noyau dans le domaine
    assert (ea.weights * grid_index.area[ea.cells]).sum() / 2.0 == pytest.approx(1.0 - ea.outside_fraction)
    tot = design_row(_obs("census"), m.likelihoods[1], grid_index)
    from amtgo.geo.crs import to_equal_area

    area = to_equal_area(box(-24.9, -25.9, -24.1, -25.1)).area / 1e6
    assert (tot.weights * grid_index.area[tot.cells]).sum() == pytest.approx(area, rel=1e-3)


def test_selection_counts_every_exclusion(grid_index: MeshIndex, configs_dir: Path) -> None:
    m = _manifest(configs_dir)
    old = datetime(2019, 1, 1, tzinfo=UTC)
    low_q = Q.model_copy(update={"construct_validity": 0.1})
    obs = [_obs("ea"), _obs("ea", valid_from=old, recorded_at=old, valid_until=old),
           _obs("ea", quality=low_q), _obs("ea", variable_id="other"), _obs("census")]
    sel = select_observations(obs, m, grid_index, SLUGS, {"synthetic_survey"})
    assert sel.excluded == {"temporal_mismatch": 1, "quality_gate": 1, "no_likelihood": 1,
                            "role_not_declared": 1}
    assert sel.used == {"synthetic_survey": 1}


def test_holdout_is_deterministic() -> None:
    ids = [f"id-{k}" for k in range(2000)]
    a = [is_holdout(i, 0.2) for i in ids]
    assert a == [is_holdout(i, 0.2) for i in ids]
    assert 0.15 < sum(a) / len(a) < 0.25


def test_manifest_rules(configs_dir: Path) -> None:
    raw = yaml.safe_load((configs_dir / "measurement" / "population_v1.yaml").read_text())
    bad = dict(raw, prior={"kind": "independent_density", "density_mean_per_km2": 20, "density_sd_per_km2": 5})
    with pytest.raises(ValueError):
        MeasurementManifest.model_validate(bad)  # marges sans prior positif
    bad2 = dict(raw)
    bad2["likelihoods"] = [dict(raw["likelihoods"][0], use="margin")]
    with pytest.raises(ValueError):
        MeasurementManifest.model_validate(bad2)  # une EA n'est pas une marge
    bad3 = dict(raw, computability=dict(raw["computability"], a_min=0.1))
    with pytest.raises(ValueError):
        MeasurementManifest.model_validate(bad3)


def test_computability_classes() -> None:
    spec = ComputabilitySpec(a_min=0.9, b_min=0.6, c_min=0.3, max_negative_sample_fraction=0.05)
    assert cell_class(0.95, 0.0, spec) is ComputabilityClass.A
    assert cell_class(0.95, 0.2, spec) is ComputabilityClass.D  # tirages négatifs : mal spécifié
    assert cell_class(0.1, 0.0, spec) is ComputabilityClass.D
    A, D = ComputabilityClass.A, ComputabilityClass.D
    assert zone_class([A, A, D, D]) is D  # médiane basse : conservatrice
    assert zone_class([]) is D
