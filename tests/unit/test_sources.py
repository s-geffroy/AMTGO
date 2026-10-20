"""M1 : manifestes de source et observations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from amtgo.core.enums import EvidenceStatus, PrivacyClass, SupportType
from amtgo.core.quality import QualityVector
from amtgo.data.observations import Observation
from amtgo.data.sources import SourceManifest, load_source_manifest
from amtgo.errors import DataLicenseError, ForbiddenSourceRole, TopologyError

Q = QualityVector(source_reliability=1, spatial_precision=1, temporal_precision=1, construct_validity=1,
                  representativeness=1, license_usability=1, privacy_usability=1)


def _raw(configs_dir: Path, name: str = "natural_earth_admin0") -> dict:
    return yaml.safe_load((configs_dir / "sources" / f"{name}.yaml").read_text())


def test_repo_manifests_valid(configs_dir: Path) -> None:
    for p in sorted((configs_dir / "sources").glob("*.yaml")):
        load_source_manifest(p)


def test_roles(configs_dir: Path) -> None:
    m = load_source_manifest(configs_dir / "sources" / "natural_earth_admin0.yaml")
    m.require_role("basemap_display")
    with pytest.raises(ForbiddenSourceRole):
        m.require_role("legal_boundary_truth")
    with pytest.raises(ForbiddenSourceRole):
        m.require_role("undeclared_role")


def test_role_overlap_refused(configs_dir: Path) -> None:
    raw = _raw(configs_dir)
    raw["roles"]["forbidden"].append("basemap_display")
    with pytest.raises(ValueError):
        SourceManifest.model_validate(raw)


def test_open_core_needs_redistribution(configs_dir: Path) -> None:
    raw = _raw(configs_dir)
    raw["license"]["redistribution"] = False
    with pytest.raises(ValueError):
        SourceManifest.model_validate(raw)


def test_unpinned_resource_refused(configs_dir: Path) -> None:
    raw = _raw(configs_dir)
    raw["retrieval"]["resources"][0]["sha256"] = None
    with pytest.raises(ValueError):
        SourceManifest.model_validate(raw)


def test_restricted_never_http(configs_dir: Path) -> None:
    raw = _raw(configs_dir)
    raw.update(access="restricted", data_zone="RESTRICTED_LOCAL", privacy_class="CONTROLLED")
    with pytest.raises(ValueError):
        SourceManifest.model_validate(raw)


def test_historical_needs_context(configs_dir: Path) -> None:
    raw = _raw(configs_dir)
    raw["default_evidence_status"] = "H"
    with pytest.raises(ValueError):
        SourceManifest.model_validate(raw)


def test_commercial_license_check(configs_dir: Path) -> None:
    raw = _raw(configs_dir, "synthetic_pilot")
    raw["license"]["commercial_use"] = False
    m = SourceManifest.model_validate(raw)
    with pytest.raises(DataLicenseError):
        m.require_license(redistribute=False, commercial=True)


def _obs(**kw: object) -> Observation:
    base: dict[str, object] = dict(
        id=Observation.make_id("s", "v", "k", datetime(2020, 1, 1, tzinfo=UTC)), source_id="s",
        variable_id="v", support_type=SupportType.POINT, geometry_wkt="POINT (10 5)",
        valid_from=datetime(2020, 1, 1, tzinfo=UTC), recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
        quality=Q, evidence_status=EvidenceStatus.DIRECT, sensitivity=PrivacyClass.PUBLIC)
    base.update(kw)
    return Observation(**base)  # type: ignore[arg-type]


def test_observation_valid() -> None:
    assert _obs().geometry() is not None


def test_observation_time_order() -> None:
    with pytest.raises(ValueError):
        _obs(valid_until=datetime(2019, 1, 1, tzinfo=UTC))


def test_geomasked_point_is_distribution() -> None:
    with pytest.raises(ValueError):
        _obs(support_type=SupportType.UNCERTAIN_POINT)
    with pytest.raises(ValueError):
        _obs(displacement_km=5.0)
    assert _obs(support_type=SupportType.UNCERTAIN_POINT, displacement_km=5.0).displacement_km == 5.0


def test_support_requirements() -> None:
    with pytest.raises(ValueError):
        _obs(support_type=SupportType.RASTER, geometry_wkt=None)
    with pytest.raises(ValueError):
        _obs(support_type=SupportType.NATIONAL, geometry_wkt=None)


def test_invalid_geometry() -> None:
    with pytest.raises(TopologyError):
        _obs(support_type=SupportType.POLYGON, geometry_wkt="POLYGON ((0 0, 1 1, 1 0, 0 1, 0 0))")
