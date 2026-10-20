"""M4 : ontologies, crosswalks probabilistes, composition."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import yaml
from shapely.geometry import box

from amtgo.core.enums import EvidenceStatus, PrivacyClass, SupportType
from amtgo.core.quality import QualityVector
from amtgo.core.uncertainty import UncertainValue
from amtgo.data.observations import Observation
from amtgo.errors import InsufficientEvidence, OntologyMappingError
from amtgo.geo.mesh import BBoxExtent, MeshDefinition, MeshFamily
from amtgo.geo.ops import create_base_mesh
from amtgo.measurement.composition import (
    CompositionManifest,
    aggregate_shares,
    effective_number,
    fit_composition,
    project,
)
from amtgo.ontology.crosswalk import compose, sample_matrices, target_space
from amtgo.ontology.model import UNMAPPED, Ontology, OntologyCrosswalk, load_crosswalk, load_ontology

BBOX = (-25.0, -26.0, -23.0, -24.0)
Q = QualityVector(source_reliability=1, spatial_precision=1, temporal_precision=1, construct_validity=1,
                  representativeness=1, license_usability=1, privacy_usability=1)


def _ont(configs_dir: Path, name: str) -> Ontology:
    return load_ontology(configs_dir / "ontologies" / f"{name}.yaml")


def _raw(configs_dir: Path, name: str) -> dict:
    return yaml.safe_load((configs_dir / "ontologies" / f"{name}.yaml").read_text())


def test_repo_ontologies_and_crosswalk_valid(configs_dir: Path) -> None:
    self_id, ext = _ont(configs_dir, "synth_self_id"), _ont(configs_dir, "synth_ext_hist")
    cw = load_crosswalk(configs_dir / "crosswalks" / "synth_self_to_ext_hist.yaml")
    cw.check_against(self_id, ext)


def test_historical_needs_context_and_status(configs_dir: Path) -> None:
    raw = _raw(configs_dir, "synth_ext_hist")
    with pytest.raises(ValueError):
        Ontology.model_validate({k: v for k, v in raw.items() if k != "historical_context"})
    with pytest.raises(ValueError):
        Ontology.model_validate(dict(raw, evidence_status="D"))


def test_hierarchy_must_be_acyclic(configs_dir: Path) -> None:
    raw = _raw(configs_dir, "synth_self_id")
    raw["concepts"][0]["parent_id"] = "beta"
    raw["concepts"][1]["parent_id"] = "alpha"
    with pytest.raises(ValueError):
        Ontology.model_validate(raw)


def test_unmapped_is_reserved(configs_dir: Path) -> None:
    raw = _raw(configs_dir, "synth_self_id")
    raw["concepts"][0]["concept_id"] = UNMAPPED
    with pytest.raises(ValueError):
        Ontology.model_validate(raw)


def _cw_raw(configs_dir: Path) -> dict:
    return yaml.safe_load((configs_dir / "crosswalks" / "synth_self_to_ext_hist.yaml").read_text())


def test_crosswalk_rows_must_sum_to_one(configs_dir: Path) -> None:
    raw = _cw_raw(configs_dir)
    raw["rows"][0]["targets"] = {"ext_a": 0.9}  # masse manquante non déclarée
    with pytest.raises(ValueError):
        OntologyCrosswalk.model_validate(raw)


def test_crosswalk_never_direct(configs_dir: Path) -> None:
    with pytest.raises(ValueError):
        OntologyCrosswalk.model_validate(dict(_cw_raw(configs_dir), evidence_status="D"))


def test_crosswalk_across_dimensions_refused(configs_dir: Path) -> None:
    """prompt §21 : aucun mapping automatique entre identité ethnoculturelle et nationale."""
    raw = _raw(configs_dir, "synth_ext_hist")
    national = Ontology.model_validate(dict(raw, ontology_id="synth_national", dimension="national"))
    cw = OntologyCrosswalk.model_validate(dict(_cw_raw(configs_dir), target_ontology="synth_national"))
    with pytest.raises(OntologyMappingError):
        cw.check_against(_ont(configs_dir, "synth_self_id"), national)


def test_crosswalk_must_cover_every_source_concept(configs_dir: Path) -> None:
    raw = _cw_raw(configs_dir)
    raw["rows"] = raw["rows"][:-1]
    cw = OntologyCrosswalk.model_validate(raw)
    with pytest.raises(OntologyMappingError):
        cw.check_against(_ont(configs_dir, "synth_self_id"), _ont(configs_dir, "synth_ext_hist"))


def test_sampled_matrices_are_stochastic_and_centered(configs_dir: Path) -> None:
    src, tgt = _ont(configs_dir, "synth_self_id"), _ont(configs_dir, "synth_ext_hist")
    cw = load_crosswalk(configs_dir / "crosswalks" / "synth_self_to_ext_hist.yaml")
    m = sample_matrices(cw, src, tgt, 4000, 0)
    assert np.allclose(m.sum(axis=2), 1.0)
    cols = target_space(tgt)
    assert m[:, 0, cols.index("ext_a")].mean() == pytest.approx(0.9, abs=0.01)
    assert np.all(m[:, 2, cols.index("ext_a")] == 0.0)  # jamais de masse hors support déclaré


def test_composition_keeps_unmapped() -> None:
    s = 10
    first = np.zeros((s, 2, 3))
    first[:, :, 0], first[:, :, 1], first[:, :, 2] = 0.6, 0.2, 0.2  # dernière colonne : UNMAPPED
    second = np.zeros((s, 2, 2))
    second[:, :, 0] = 1.0
    out = compose(first, second, unmapped_index_mid=2)
    assert np.allclose(out.sum(axis=2), 1.0)
    assert np.allclose(out[:, :, -1], 0.2 + 0.0)  # UNMAPPED reste UNMAPPED


def _manifest(configs_dir: Path) -> CompositionManifest:
    return CompositionManifest.model_validate(
        yaml.safe_load((configs_dir / "composition" / "self_id_v1.yaml").read_text()))


def _resp(x: float, y: float, counts: dict[str, int], **kw: object) -> Observation:
    t = datetime(2025, 6, 1, tzinfo=UTC)
    base: dict[str, object] = dict(
        id=Observation.make_id("src", "identity_self_counts", f"{x},{y},{counts}", t), source_id="src",
        variable_id="identity_self_counts", ontology_id="synth_self_id",
        support_type=SupportType.UNCERTAIN_POINT, geometry_wkt=f"POINT ({x} {y})", displacement_km=3.0,
        valid_from=t, recorded_at=t, value=UncertainValue.exact(float(sum(counts.values()))),
        attributes={"counts": counts, "design_weight": 100.0}, quality=Q,
        evidence_status=EvidenceStatus.DIRECT, sensitivity=PrivacyClass.PUBLIC)
    base.update(kw)
    return Observation(**base)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def mesh():  # type: ignore[no-untyped-def]
    d = MeshDefinition(mesh_id="cm", family=MeshFamily.GRID_LAEA, resolution=4, grid_base_km=400,
                       extent=BBoxExtent(bbox=BBOX))
    return create_base_mesh(d, box(*BBOX))


def test_composition_informs_observed_cells_only(mesh, configs_dir: Path) -> None:  # type: ignore[no-untyped-def]
    obs = [_resp(-24.9, -25.9, {"alpha": 25, "beta": 0, "gamma": 0, "delta": 0})] * 1
    fit = fit_composition(mesh, obs, _manifest(configs_dir), _ont(configs_dir, "synth_self_id"), "src", 300, 0)
    assert np.allclose(fit.samples.sum(axis=2), 1.0)
    info = fit.information_ratio
    observed = fit.respondents > 0
    assert observed.any() and (~observed).any()
    assert info[observed].mean() > info[~observed].mean()
    # La cellule observée penche vers alpha ; c'est une part, pas une étiquette.
    j = int(np.argmax(fit.respondents))
    assert fit.samples[:, j, 0].mean() > 0.25


def test_composition_rejects_foreign_categories(mesh, configs_dir: Path) -> None:  # type: ignore[no-untyped-def]
    obs = [_resp(-24.0, -25.0, {"alpha": 5, "omega": 3})]
    with pytest.raises(OntologyMappingError):
        fit_composition(mesh, obs, _manifest(configs_dir), _ont(configs_dir, "synth_self_id"), "src", 50, 0)


def test_composition_needs_design_weights_when_declared(mesh, configs_dir: Path) -> None:  # type: ignore[no-untyped-def]
    obs = [_resp(-24.0, -25.0, {"alpha": 5}, attributes={"counts": {"alpha": 5}})]
    with pytest.raises(InsufficientEvidence):
        fit_composition(mesh, obs, _manifest(configs_dir), _ont(configs_dir, "synth_self_id"), "src", 50, 0)


def test_projection_and_aggregation(mesh, configs_dir: Path) -> None:  # type: ignore[no-untyped-def]
    src, tgt = _ont(configs_dir, "synth_self_id"), _ont(configs_dir, "synth_ext_hist")
    cw = load_crosswalk(configs_dir / "crosswalks" / "synth_self_to_ext_hist.yaml")
    fit = fit_composition(mesh, [_resp(-24.0, -25.0, {"gamma": 20, "delta": 5})], _manifest(configs_dir),
                          src, "src", 100, 0)
    proj = project(fit, sample_matrices(cw, src, tgt, 100, 0), tgt)
    assert proj.categories[-1] == UNMAPPED and np.allclose(proj.samples.sum(axis=2), 1.0)
    pop = np.ones((100, len(mesh)))
    w = np.ones((1, len(mesh)))
    agg = aggregate_shares(fit.samples, pop, w)
    assert agg.shape == (100, 1, 4) and np.allclose(agg.sum(axis=2), 1.0)
    eng = effective_number(agg)
    assert np.all((eng >= 1.0) & (eng <= 4.0 + 1e-9))
