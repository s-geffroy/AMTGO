"""Prior log-normal corrélé (niveau commun, blocs, terme propre) : R2_REPORT, Challenge 1.

Propriétés qualitatives (ADR-0010) :
- l'incertitude a priori d'un grand agrégat ne dépend plus de la finesse du
  maillage, alors qu'elle s'effondre avec un prior indépendant ;
- une observation informe les cellules non observées par les facteurs partagés ;
- sans corrélation déclarée, le comportement indépendant est inchangé.
"""

from __future__ import annotations

import numpy as np
import pytest

from amtgo.geo.mesh import BBoxExtent, MeshDefinition, MeshFamily, bbox_geometry
from amtgo.geo.ops import create_base_mesh
from amtgo.measurement.engine import factor_mixing
from amtgo.measurement.fusion import LogNormalPrior, fuse_lognormal, sample_prior
from amtgo.measurement.likelihoods import DesignRow, MeshIndex

EXT = BBoxExtent(bbox=(-25.0, -26.0, -22.0, -23.0))  # Atlantique Sud : aucune population réelle


def index(level: int) -> MeshIndex:
    d = MeshDefinition(mesh_id=f"cp_l{level}", family=MeshFamily.GRID_LAEA, resolution=level,
                       grid_base_km=400, extent=EXT)
    return MeshIndex(create_base_mesh(d, bbox_geometry(EXT)))


def prior(idx: MeshIndex, correlated: bool, level_sd: float = 0.1, block_sd: float = 0.25,
          cell_sd: float = 1.0) -> LogNormalPrior:
    n = len(idx)
    mu = np.full(n, np.log(20.0))
    if not correlated:
        return LogNormalPrior(mu, np.full(n, cell_sd**2), idx.area)
    mx, nb = factor_mixing(idx, 50.0)
    vz = np.concatenate([[level_sd**2], np.full(nb, block_sd**2), np.full(n, cell_sd**2)])
    return LogNormalPrior(mu, np.full(n, level_sd**2 + block_sd**2 + cell_sd**2), idx.area, mx, vz)


def test_mixing_structure() -> None:
    idx = index(5)
    mx, nb = factor_mixing(idx, 50.0)
    assert mx.shape == (len(idx), 1 + nb + len(idx)) and 1 < nb < len(idx)
    assert np.all(mx.sum(axis=1) == 3)  # niveau + un bloc + terme propre, pour chaque cellule
    assert np.all(mx[:, 0].toarray() == 1)


def _total_cv(p: LogNormalPrior) -> float:
    t = sample_prior(p, 4000, 3).sum(axis=1)
    return float(t.std() / t.mean())


def test_aggregate_uncertainty_does_not_collapse_with_mesh_refinement() -> None:
    coarse, fine = index(5), index(7)
    ind = _total_cv(prior(coarse, False)), _total_cv(prior(fine, False))
    cor = _total_cv(prior(coarse, True)), _total_cv(prior(fine, True))
    assert ind[1] < 0.5 * ind[0]  # prior indépendant : l'agrégat se resserre avec le maillage
    assert cor[1] == pytest.approx(cor[0], rel=0.25)  # prior corrélé : stable
    assert cor[1] > 0.1  # au moins le niveau commun


def test_observation_informs_unobserved_cells_through_shared_level() -> None:
    idx = index(5)
    p = prior(idx, True, level_sd=0.3, block_sd=0.05)
    observed = np.arange(0, len(idx), 5)
    # Comptes partout 50 % au-dessus du prior, sur une cellule sur cinq.
    rows = [DesignRow(f"o{k}", "s", np.array([k]), np.array([1.0]), 1.5 * 20.0 * idx.area[k],
                      (0.02 * 30.0 * idx.area[k]) ** 2, 0.0) for k in observed]
    post, info = fuse_lognormal(p, rows, 200, 1)
    assert info.converged
    unobserved = np.setdiff1d(np.arange(len(idx)), observed)
    ratio = post.samples[:, unobserved].sum(axis=1).mean() / sample_prior(p, 2000, 2)[:, unobserved].sum(axis=1).mean()
    assert ratio > 1.2  # le facteur commun appris remonte aussi les cellules non observées
    ind_post, _ = fuse_lognormal(prior(idx, False), rows, 200, 1)
    ind_ratio = (ind_post.samples[:, unobserved].sum(axis=1).mean()
                 / sample_prior(prior(idx, False), 2000, 2)[:, unobserved].sum(axis=1).mean())
    assert ind_ratio == pytest.approx(1.0, abs=0.1)  # prior indépendant : rien ne se propage


def test_identity_mixing_matches_independent_prior() -> None:
    idx = index(4)
    p = prior(idx, False)
    explicit = LogNormalPrior(p.log_mean, p.log_var, p.area, *_identity(len(idx), p.log_var))
    rows = [DesignRow("o", "s", np.array([0, 1]), np.array([1.0, 1.0]), 5000.0, 1e4, 0.0)]
    a, _ = fuse_lognormal(p, rows, 50, 4)
    b, _ = fuse_lognormal(explicit, rows, 50, 4)
    np.testing.assert_allclose(a.samples, b.samples, rtol=1e-9)


def _identity(n: int, v: np.ndarray) -> tuple:
    from scipy import sparse

    return sparse.identity(n, format="csr"), v


@pytest.mark.parametrize("correlated", [False, True])
def test_raster_prior_is_centered_on_the_raster_expectation(configs_dir, correlated: bool) -> None:  # type: ignore[no-untyped-def]
    """WorldPop estime une espérance : E[total a priori] = total du raster (et non e^{σ²/2} fois plus)."""
    import yaml

    from amtgo.measurement.engine import prior_for
    from amtgo.measurement.manifest import MeasurementManifest

    raw = yaml.safe_load((configs_dir / "measurement" / "gha_population_2021.yaml").read_text())
    if not correlated:
        raw["prior"].pop("correlation")
    m = MeasurementManifest.model_validate(raw)
    idx = index(5)
    density = np.random.default_rng(5).gamma(2.0, 30.0, len(idx))
    p = prior_for(idx, m, density)
    assert isinstance(p, LogNormalPrior)
    total = sample_prior(p, 20000, 9).sum(axis=1).mean()
    assert total == pytest.approx(float((density * idx.area).sum()), rel=0.03)
