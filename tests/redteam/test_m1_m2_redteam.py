"""Red-team permanents applicables à M0–M2 (prompt §57, 05 §15).

Chaque contournement trouvé devient un test ici.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from amtgo.core.enums import EvidenceStatus, PrivacyClass
from amtgo.data import ingestion
from amtgo.data.adapters.synthetic import SyntheticAdapter
from amtgo.data.ingestion import IngestRequest, ingest_source
from amtgo.data.sources import SourceManifest, load_source_manifest
from amtgo.errors import (
    DataLicenseError,
    ForbiddenSourceRole,
    PrivacyViolation,
    ProvenanceError,
)
from amtgo.privacy.guard import ExportLayer, PrivacyAction, evaluate, require_allowed


def _synthetic(configs_dir: Path) -> SourceManifest:
    return load_source_manifest(configs_dir / "sources" / "synthetic_pilot.yaml")


def test_forbidden_role_refused_before_any_fetch(configs_dir: Path, tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    called = []
    monkeypatch.setattr(SyntheticAdapter, "fetch", lambda *a, **k: called.append(1))
    with pytest.raises(ForbiddenSourceRole):
        ingest_source(_synthetic(configs_dir), IngestRequest(roles=("real_world_inference",)),
                      tmp_path / "c", tmp_path / "o")
    assert not called


def test_ne_cannot_be_legal_truth_or_population(configs_dir: Path) -> None:
    m = load_source_manifest(configs_dir / "sources" / "natural_earth_admin0.yaml")
    for role in ("legal_boundary_truth", "local_population_counts", "group_territory_inference"):
        with pytest.raises(ForbiddenSourceRole):
            m.require_role(role)


def test_redistribution_refused_when_license_forbids(configs_dir: Path, tmp_path: Path) -> None:
    raw = yaml.safe_load((configs_dir / "sources" / "synthetic_pilot.yaml").read_text())
    raw.update(access="restricted", data_zone="RESTRICTED_LOCAL", privacy_class="CONTROLLED")
    raw["license"]["redistribution"] = False
    m = SourceManifest.model_validate(raw)
    with pytest.raises(DataLicenseError):
        ingest_source(m, IngestRequest(roles=("population_prior",), redistribute=True),
                      tmp_path / "c", tmp_path / "o")


def test_observation_less_protected_than_source(configs_dir: Path, tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    raw = yaml.safe_load((configs_dir / "sources" / "synthetic_pilot.yaml").read_text())
    raw.update(access="restricted", data_zone="RESTRICTED_LOCAL", privacy_class="CONTROLLED")
    m = SourceManifest.model_validate(raw)
    original = SyntheticAdapter.normalize

    def leaky(self, manifest, files, recorded_at):  # type: ignore[no-untyped-def]
        for o in original(self, manifest, files, recorded_at):
            yield o.model_copy(update={"sensitivity": PrivacyClass.PUBLIC})

    monkeypatch.setattr(SyntheticAdapter, "normalize", leaky)
    with pytest.raises(PrivacyViolation):
        ingest_source(m, IngestRequest(roles=("population_prior",)), tmp_path / "c", tmp_path / "o")


def test_silent_evidence_promotion_refused(configs_dir: Path, tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    raw = yaml.safe_load((configs_dir / "sources" / "synthetic_pilot.yaml").read_text())
    raw["default_evidence_status"] = "M"
    m = SourceManifest.model_validate(raw)
    original = SyntheticAdapter.normalize

    def promote(self, manifest, files, recorded_at):  # type: ignore[no-untyped-def]
        for o in original(self, manifest, files, recorded_at):
            yield o.model_copy(update={"evidence_status": EvidenceStatus.DIRECT})

    monkeypatch.setattr(SyntheticAdapter, "normalize", promote)
    with pytest.raises(ProvenanceError):
        ingest_source(m, IngestRequest(roles=("population_prior",)), tmp_path / "c", tmp_path / "o")


def test_checksum_mismatch_refused(ne_mini: Path, configs_dir: Path, tmp_path: Path) -> None:
    m = load_source_manifest(configs_dir / "sources" / "ne_mini.yaml")
    target = Path(m.retrieval.resources[0].path or "")
    target.write_text(target.read_text().replace("Testland A", "Testland Z"))
    with pytest.raises(ProvenanceError):
        ingest_source(m, IngestRequest(roles=("basemap_display",)), tmp_path / "c", tmp_path / "o")


def test_provenance_rooted(configs_dir: Path, tmp_path: Path) -> None:
    from amtgo.core.provenance import ProvenanceGraph

    m = _synthetic(configs_dir)
    r = ingest_source(m, IngestRequest(roles=("population_prior",)), tmp_path / "c", tmp_path / "o",
                      recorded_at=datetime(2025, 6, 1, tzinfo=UTC))
    g = ProvenanceGraph(r.records)
    g.require_rooted(f"observations:{r.observations_hash}", {str(r.source.id)})
    # Une couche dont on aurait perdu la lignée est détectée.
    with pytest.raises(ProvenanceError):
        g.require_rooted("observations:sha256:unknown", {str(r.source.id)})


def test_observations_roundtrip_and_hash_excludes_clock(configs_dir: Path, tmp_path: Path) -> None:
    m = _synthetic(configs_dir)
    a = ingest_source(m, IngestRequest(roles=("population_prior",)), tmp_path / "c", tmp_path / "a",
                      recorded_at=datetime(2025, 1, 1, tzinfo=UTC))
    b = ingest_source(m, IngestRequest(roles=("population_prior",)), tmp_path / "c", tmp_path / "b",
                      recorded_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert a.observations_hash == b.observations_hash
    back = ingestion.read_observations(a.observations_path)
    assert ingestion.observations_content_hash(back) == a.observations_hash


@pytest.mark.parametrize("layer,action", [
    (ExportLayer("basemap", PrivacyClass.PUBLIC, False, False, False, 10), PrivacyAction.ALLOW),
    (ExportLayer("groups", PrivacyClass.PUBLIC, True, True, False, 10), PrivacyAction.RESTRICT),
    (ExportLayer("routes", PrivacyClass.PUBLIC, False, False, True, 10), PrivacyAction.RESTRICT),
    (ExportLayer("pop", PrivacyClass.PUBLIC, True, False, False, 10), PrivacyAction.AGGREGATE),
    (ExportLayer("micro", PrivacyClass.PROHIBITED, False, False, False, 10), PrivacyAction.SUPPRESS),
    (ExportLayer("ctrl", PrivacyClass.CONTROLLED, False, False, False, 10), PrivacyAction.RESTRICT),
])
def test_privacy_guard(layer: ExportLayer, action: PrivacyAction) -> None:
    assert evaluate(layer).action is action
    if action is not PrivacyAction.ALLOW:
        with pytest.raises(PrivacyViolation):
            require_allowed(layer)


def test_no_forbidden_functions_exist() -> None:
    """prompt §92 et §3 : aucune fonction globale ambiguë ou interdite dans le paquet."""
    import pkgutil

    import amtgo

    forbidden = {"maximize_ethnic_homogeneity", "ethnic_score", "territorial_coherence",
                 "optimize_africa", "best_solution", "is_viable"}
    for mod in pkgutil.walk_packages(amtgo.__path__, "amtgo."):
        module = __import__(mod.name, fromlist=["_"])
        assert not forbidden & set(dir(module)), mod.name


def test_synthetic_points_inside_declared_extent(configs_dir: Path, tmp_path: Path) -> None:
    """Régression : les grappes étaient tirées dans un rectangle LAEA tourné, hors emprise."""
    from shapely.geometry import box

    m = _synthetic(configs_dir)
    r = ingest_source(m, IngestRequest(roles=("population_prior",)), tmp_path / "c", tmp_path / "o")
    extent = box(*m.retrieval.parameters["bbox"])
    for o in ingestion.read_observations(r.observations_path):
        g = o.geometry()
        assert g is not None and extent.contains(g)
