"""M0 : types transverses — statuts de preuve, qualité, incertitude, canonique, logs."""

from __future__ import annotations

import json
import math
import uuid

import pytest

from amtgo.core.enums import EvidenceStatus, PrivacyClass, RecommendationStatus
from amtgo.core.provenance import ProvenanceGraph, ProvenanceRecord
from amtgo.core.quality import QualityVector
from amtgo.core.uncertainty import DistributionType, UncertainValue
from amtgo.errors import InsufficientEvidence, ProvenanceError
from amtgo.utils.canonical import canonical_json, content_hash, stable_uuid
from amtgo.utils.logging import log_event

Q = dict(source_reliability=1, spatial_precision=1, temporal_precision=1, construct_validity=1,
         representativeness=1, license_usability=1, privacy_usability=1)


class TestEvidence:
    def test_model_never_becomes_direct(self) -> None:
        assert EvidenceStatus.combine([EvidenceStatus.DIRECT, EvidenceStatus.MODEL]) is EvidenceStatus.MODEL
        assert EvidenceStatus.DIRECT.through_model() is EvidenceStatus.MODEL
        assert EvidenceStatus.UNKNOWN.through_model() is EvidenceStatus.UNKNOWN

    def test_empty_is_unknown(self) -> None:
        assert EvidenceStatus.combine([]) is EvidenceStatus.UNKNOWN

    def test_short_codes(self) -> None:
        assert [s.value for s in EvidenceStatus] == ["D", "P", "M", "H", "U"]


class TestPrivacyClass:
    def test_default_is_not_public(self) -> None:
        assert PrivacyClass.most_restrictive([]) is PrivacyClass.CONTROLLED

    def test_most_restrictive(self) -> None:
        assert PrivacyClass.most_restrictive([PrivacyClass.PUBLIC, PrivacyClass.SENSITIVE]) is PrivacyClass.SENSITIVE

    def test_no_sharp_border_when_not_identifiable(self) -> None:
        assert not RecommendationStatus.NOT_IDENTIFIABLE.allows_sharp_border
        assert not RecommendationStatus.DATA_LIMITED.allows_sharp_border
        assert RecommendationStatus.ROBUST.allows_sharp_border


class TestQuality:
    def test_no_scalar_score(self) -> None:
        q = QualityVector(**Q)
        with pytest.raises(TypeError):
            float(q)
        assert not hasattr(q, "quality_score")

    def test_bounds(self) -> None:
        with pytest.raises(ValueError):
            QualityVector(**{**Q, "spatial_precision": 1.2})

    def test_elementwise_min(self) -> None:
        a = QualityVector(**Q)
        b = QualityVector(**{**Q, "temporal_precision": 0.2})
        assert a.elementwise_min(b).temporal_precision == 0.2


class TestUncertainValue:
    def test_from_samples(self) -> None:
        u = UncertainValue.from_samples([0.1, 0.2, 0.3, 0.4])
        assert u.distribution_type is DistributionType.EMPIRICAL
        assert u.lower <= u.mean <= u.upper  # type: ignore[operator]
        assert u.exceedance_probability(0.25) == 0.5

    def test_bounds_only_refuses_probability(self) -> None:
        u = UncertainValue.bounds(0.0, 1.0)
        assert u.mean is None
        with pytest.raises(InsufficientEvidence):
            u.exceedance_probability(0.5)
        with pytest.raises(InsufficientEvidence):
            u.cvar(0.9)

    def test_exact(self) -> None:
        assert UncertainValue.exact(0.3).exceedance_probability(0.2) == 1.0

    def test_cvar_is_tail_mean(self) -> None:
        u = UncertainValue.from_samples(list(range(10)))
        assert u.cvar(0.8) == pytest.approx(8.5)

    def test_skewed_samples_mean_outside_central_interval(self) -> None:
        """Régression M5 : moyenne hors de l'intervalle à 90 % pour une loi très asymétrique."""
        samples = [0.0] * 97 + [100.0] * 3
        u = UncertainValue.from_samples(samples)
        assert u.mean == pytest.approx(3.0) and u.upper == pytest.approx(0.0)

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            UncertainValue(mean=2.0, lower=0.0, upper=1.0, distribution_type=DistributionType.NORMAL)
        with pytest.raises(ValueError):
            UncertainValue(mean=None, distribution_type=DistributionType.EMPIRICAL)
        with pytest.raises(ValueError):
            UncertainValue(mean=0.5, lower=0, upper=1, distribution_type=DistributionType.UNKNOWN)


class TestCanonical:
    def test_key_order_irrelevant(self) -> None:
        assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})
        assert content_hash({"b": 1, "a": 2}) == content_hash({"a": 2, "b": 1})

    def test_stable_uuid(self) -> None:
        assert stable_uuid("x", {"a": 1}) == stable_uuid("x", {"a": 1})
        assert stable_uuid("x", {"a": 1}) != stable_uuid("y", {"a": 1})

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError):
            canonical_json({"a": math.nan})


class TestProvenance:
    def test_record_id_ignores_clock(self) -> None:
        a = ProvenanceRecord.create("t", ["i"], ["o"], {"p": 1})
        b = ProvenanceRecord.create("t", ["i"], ["o"], {"p": 1})
        assert a.record_id == b.record_id

    def test_lineage(self) -> None:
        g = ProvenanceGraph([
            ProvenanceRecord.create("ingest", ["src:1"], ["obs:1"]),
            ProvenanceRecord.create("field", ["obs:1"], ["field:1"]),
        ])
        g.require_rooted("field:1", {"src:1"})
        with pytest.raises(ProvenanceError):
            g.require_rooted("field:1", {"src:2"})
        with pytest.raises(ProvenanceError):
            g.require_rooted("orphan", {"src:1"})

    def test_no_output_refused(self) -> None:
        with pytest.raises(ProvenanceError):
            ProvenanceRecord.create("t", ["i"], [])


class TestLogging:
    def test_one_json_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        log_event("x.y", run_id=str(uuid.uuid4()), stage="ingest", status="done")
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1
        rec = json.loads(out[0])
        assert rec["event"] == "x.y" and "ts" in rec

    def test_unknown_field_refused(self) -> None:
        with pytest.raises(ValueError):
            log_event("x", respondent_name="nope")
