"""M9 : composeur institutionnel — manifeste, leviers, invariants, conclusions."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from amtgo.core.channels import IntegChannel
from amtgo.institutions.competences import Domain, check_exclusive
from amtgo.institutions.composer import ComposerManifest, Configuration, Lever, LeverSpec, apply_lever
from amtgo.manifests.normative import RightsThresholds
from amtgo.validation import composer_worlds as I

RIGHTS = RightsThresholds(severe_domination_threshold=0.5, severe_domination_probability_max=0.05,
                          urgent_domination_threshold=0.7, urgent_probability=0.5)
WEIGHTS = {c: 1.0 for c in IntegChannel}


def _base() -> tuple[Configuration, Any]:
    _, part = I.world(0.15)
    return Configuration(I._institutions(part), []), part


def test_search_order_is_enforced() -> None:
    raw = I.manifest().model_dump(mode="json")
    raw["levers"] = list(reversed(raw["levers"]))
    with pytest.raises(ValidationError, match="ordre de recherche"):
        ComposerManifest.model_validate(raw)


def test_lever_requires_causal_effect() -> None:
    with pytest.raises(ValidationError, match="effet causal"):
        LeverSpec(lever=Lever.RIGHTS_ENFORCEMENT, target_checks=0.8)
    LeverSpec(lever=Lever.SOVEREIGNTY)  # renvoyée à M10 : pas d'effet requis ici


def test_rights_enforcement_is_partial() -> None:
    cfg, _ = _base()
    spec = LeverSpec(lever=Lever.RIGHTS_ENFORCEMENT, effect="x", target_checks=0.8)
    out = apply_lever(cfg, spec, 0.5, I.manifest(), [])
    assert out.institutions["state"][0].rights.get(Domain.EXECUTIVE_POWER) == pytest.approx(0.5)  # 0,2 + 0,5·0,6
    assert cfg.institutions["state"][0].rights.get(Domain.EXECUTIVE_POWER) == pytest.approx(0.2)  # pas d'effet de bord


def test_devolution_preserves_exclusivity() -> None:
    cfg, _ = _base()
    spec = LeverSpec(lever=Lever.TERRITORIAL_AUTONOMY, effect="x",
                     domains=(Domain.CULTURE_LANGUAGE, Domain.PUBLIC_SERVICES), shift=0.6)
    out = apply_lever(cfg, spec, 0.9, I.manifest(), [])
    up, lo = out.institutions["state"][0].competences, out.institutions["district"][0].competences
    check_exclusive([up, lo], [Domain.CULTURE_LANGUAGE, Domain.PUBLIC_SERVICES, Domain.LOCAL_GOVERNMENT])
    assert lo.get(Domain.CULTURE_LANGUAGE) > I.LOWER[Domain.CULTURE_LANGUAGE]


def test_representation_raises_threshold() -> None:
    cfg, _ = _base()
    out = apply_lever(cfg, LeverSpec(lever=Lever.REPRESENTATION, effect="x", threshold=0.67), 1.0, I.manifest(), [])
    assert out.institutions["state"][0].default_decision.threshold == pytest.approx(0.67)


def test_overlay_without_effect_or_members_is_not_created() -> None:
    cfg, part = _base()
    spec = LeverSpec(lever=Lever.FUNCTIONAL_OVERLAY, effect="x", channels=("network",))  # type: ignore[arg-type]
    assert apply_lever(cfg, spec, 0.0, I.manifest(), part.cell_ids).overlays == []  # μ = 0 : rien
    assert apply_lever(cfg, spec, 0.4, I.manifest(), []).overlays == []  # aucune cellule frontalière


def test_sovereignty_is_not_a_fixed_geometry_lever() -> None:
    cfg, _ = _base()
    with pytest.raises(ValueError, match="M10"):
        apply_lever(cfg, LeverSpec(lever=Lever.SOVEREIGNTY), 1.0, I.manifest(), [])


def test_world_i_properties_hold() -> None:
    failed = [(t, v) for t, ok, v in I.checks(I.evaluate_all(RIGHTS, WEIGHTS)) if not ok]
    assert not failed, failed
