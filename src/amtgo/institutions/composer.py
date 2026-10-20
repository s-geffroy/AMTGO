"""Composeur institutionnel à géométrie fixe (prompt §39, 07 §12, 11 phase 4).

À géométrie fixe, le composeur teste des **leviers** dans l'ordre de recherche du
§39 — application des droits, représentation, droits linguistiques, overlay
fonctionnel, autonomie fiscale, autonomie territoriale, fédération — avant tout
changement de frontière. Confédération et souveraineté exigent de changer la
géométrie de la souveraineté : elles sont renvoyées à l'optimiseur (M10).

Chaque levier est un changement de **vecteurs primitifs** (garde-fous C,
seuils de décision, compétences A, overlay μ), jamais une étiquette. Son effet
réel passe par une efficacité tirée de la bibliothèque causale gelée : le levier
est évalué aux deux bornes de cette efficacité (ensemble d'ambiguïté, 04 §11).
Un levier dont l'effet est inconnu n'est pas évalué : il ne « résout » jamais rien.

Conclusions possibles (le gate exige de pouvoir conclure sans redécoupage) :

- ``NO_CHANGE`` : le statu quo satisfait déjà la contrainte de droits ;
- ``NO_TERRITORIAL_CHANGE_SUFFICIENT`` : un levier (ou une suite de leviers dans
  l'ordre) lève toute violation même à la borne basse de son efficacité ;
- ``INSTITUTIONAL_UNCERTAIN`` : seulement à la borne haute ;
- ``INSTITUTIONAL_INSUFFICIENT_AT_FIXED_GEOMETRY`` : aucun ; des options
  territoriales restent à tester (M10) — ce n'est **pas** une recommandation de
  frontière.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from amtgo.causal.library import CausalAnswer
from amtgo.core.channels import FragChannel, IntegChannel
from amtgo.domination.engine import domination
from amtgo.fragmentation.engine import fragmentation
from amtgo.geo.partition import Partition
from amtgo.identity.reification import alignment
from amtgo.identity.state import BoundedSalienceResponse, SocialState
from amtgo.infrastructure.hyperedges import Hyperedge, HyperedgeType
from amtgo.institutions.competences import CompetenceVector, Domain, Institution, RightsProfile
from amtgo.integration.engine import integration
from amtgo.manifests.normative import RightsThresholds
from amtgo.utils.canonical import content_hash


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Lever(StrEnum):
    """Ordre de recherche du §39 (ordre de recherche, pas doctrine juridique)."""

    RIGHTS_ENFORCEMENT = "rights_enforcement"
    REPRESENTATION = "representation"
    LANGUAGE_RIGHTS = "language_rights"
    FUNCTIONAL_OVERLAY = "functional_overlay"
    FISCAL_AUTONOMY = "fiscal_autonomy"
    TERRITORIAL_AUTONOMY = "territorial_autonomy"
    FEDERATION = "federation"
    CONFEDERATION = "confederation"
    SOVEREIGNTY = "sovereignty"

    @property
    def rank(self) -> int:
        return list(Lever).index(self)

    @property
    def fixed_geometry(self) -> bool:
        return self not in (Lever.CONFEDERATION, Lever.SOVEREIGNTY)


_DEVOLUTION = (Lever.FISCAL_AUTONOMY, Lever.TERRITORIAL_AUTONOMY, Lever.FEDERATION)


class LeverSpec(_Strict):
    lever: Lever
    effect: str | None = None  # clé de la bibliothèque causale (efficacité ou μ)
    domains: tuple[Domain, ...] = ()  # () : tous les domaines
    target_checks: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold: float | None = Field(default=None, ge=0.5, lt=1.0)
    shift: float | None = Field(default=None, gt=0.0, le=1.0)
    channels: tuple[FragChannel, ...] = ()

    @model_validator(mode="after")
    def _params(self) -> Self:
        need = {Lever.RIGHTS_ENFORCEMENT: "target_checks", Lever.LANGUAGE_RIGHTS: "target_checks",
                Lever.REPRESENTATION: "threshold", Lever.FUNCTIONAL_OVERLAY: "channels"}
        for lv in _DEVOLUTION:
            need[lv] = "shift"
        if self.lever.fixed_geometry:
            if self.effect is None:
                raise ValueError(f"{self.lever} : effet causal obligatoire (jamais un coefficient en dur)")
            if not getattr(self, need[self.lever]):
                raise ValueError(f"{self.lever} : paramètre {need[self.lever]} requis")
        if self.lever is Lever.LANGUAGE_RIGHTS and not self.domains:
            raise ValueError("language_rights : domaines requis (ex. culture_language)")
        return self


class CostModel(_Strict):
    """Coût institutionnel C_inst (02 §15) : objectif séparé, jamais additionné à D/F/I. PROVISOIRE."""

    units: str
    coordination_per_shared_domain: float = Field(ge=0)  # domaine partagé entre niveaux
    enforcement_per_check_unit: float = Field(ge=0)  # par unité de garde-fou ajoutée, par juridiction
    threshold_change_per_unit: float = Field(ge=0)
    overlay_per_cell_share: float = Field(ge=0)  # par part des cellules couvertes


class ComposerManifest(_Strict):
    composer_id: str
    version: str
    description: str
    upper_level: str
    local_level: str
    levers: tuple[LeverSpec, ...] = Field(min_length=1)
    salience_effect: str  # institutionnalisation → saillance (réification, 04 §16)
    horizon_years: float = Field(gt=0)
    overlay_ring: int = Field(ge=0, le=5)  # anneaux de cellules autour des frontières d'État
    cost: CostModel

    @model_validator(mode="after")
    def _order(self) -> Self:
        ranks = [lv.lever.rank for lv in self.levers]
        if ranks != sorted(ranks) or len(set(ranks)) != len(ranks):
            raise ValueError("leviers : ordre de recherche du §39, chacun au plus une fois")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(self)

    @property
    def effect_keys(self) -> list[str]:
        return sorted({lv.effect for lv in self.levers if lv.effect} | {self.salience_effect})


@dataclass(frozen=True)
class Configuration:
    institutions: dict[str, list[Institution]]
    overlays: list[Hyperedge]


def _with_rights(inst: Institution, domains: tuple[Domain, ...], target: float, e: float) -> Institution:
    doms = domains or tuple(Domain)
    checks = dict(inst.rights.checks)
    for d in doms:
        c = inst.rights.get(d)
        if target > c:
            checks[d] = c + e * (target - c)
    return inst.model_copy(update={"rights": RightsProfile(checks=checks, default=inst.rights.default)})


def apply_lever(cfg: Configuration, spec: LeverSpec, e: float, manifest: ComposerManifest,
                border_cells: list[str]) -> Configuration:
    """Applique un levier d'efficacité ``e`` (∈ [0,1], ou μ pour un overlay)."""
    up, lo = manifest.upper_level, manifest.local_level
    insts = {k: list(v) for k, v in cfg.institutions.items()}
    overlays = list(cfg.overlays)
    if spec.lever in (Lever.RIGHTS_ENFORCEMENT, Lever.LANGUAGE_RIGHTS):
        assert spec.target_checks is not None
        for level in insts:
            insts[level] = [_with_rights(i, spec.domains, spec.target_checks, e) for i in insts[level]]
    elif spec.lever is Lever.REPRESENTATION:
        assert spec.threshold is not None
        new = []
        for i in insts[up]:
            q = i.default_decision.threshold
            rule = i.default_decision.model_copy(update={"threshold": q + e * max(0.0, spec.threshold - q)})
            new.append(i.model_copy(update={"default_decision": rule}))
        insts[up] = new
    elif spec.lever is Lever.FUNCTIONAL_OVERLAY:
        if len(border_cells) >= 2 and e > 0:
            overlays.append(Hyperedge(hyperedge_id=f"overlay_{spec.lever.value}", type=HyperedgeType.TRADE,
                                      members=tuple(border_cells),
                                      mitigation={c: float(e) for c in spec.channels}))
    elif spec.lever in _DEVOLUTION:
        assert spec.shift is not None
        doms = spec.domains or tuple(Domain)
        upper_auth = dict(insts[up][0].competences.authority)
        lower_auth = dict(insts[lo][0].competences.authority)
        for d in doms:
            moved = e * spec.shift * upper_auth.get(d, 0.0)
            upper_auth[d] = upper_auth.get(d, 0.0) - moved
            lower_auth[d] = lower_auth.get(d, 0.0) + moved
        insts[up] = [i.model_copy(update={"competences": CompetenceVector(authority=upper_auth)}) for i in insts[up]]
        insts[lo] = [i.model_copy(update={"competences": CompetenceVector(authority=lower_auth)}) for i in insts[lo]]
    else:
        raise ValueError(f"{spec.lever} : exige un changement de géométrie de la souveraineté (M10)")
    return Configuration(insts, overlays)


def institutionalization(state: SocialState, partition: Partition, cfg: Configuration) -> float:
    """Indice d'institutionnalisation des clivages : Σ_d Σ_niveau A · alignement(niveau) / |D|."""
    names = [lv.name for lv in partition.levels]
    align = {lv: float(alignment(state, partition, level=names.index(lv)).mean or 0.0) for lv in names}
    total = 0.0
    for d in Domain:
        total += sum(cfg.institutions[lv][0].competences.get(d) * align[lv] for lv in names if cfg.institutions[lv])
    return total / len(Domain)


def _cost(cfg: Configuration, base: Configuration, manifest: ComposerManifest, n_cells: int) -> tuple[float, int]:
    c = manifest.cost
    cost, complexity = 0.0, 0
    up, lo = manifest.upper_level, manifest.local_level
    for d in Domain:
        a_up, a_lo = cfg.institutions[up][0].competences.get(d), cfg.institutions[lo][0].competences.get(d)
        b_up = base.institutions[up][0].competences.get(d)
        if 0 < a_up < 1 and 0 < a_lo < 1:
            cost += c.coordination_per_shared_domain
        if abs(a_up - b_up) > 1e-12:
            complexity += 1
    for level, insts in cfg.institutions.items():
        for i, b in zip(insts, base.institutions[level], strict=True):
            added = sum(max(0.0, i.rights.get(d) - b.rights.get(d)) for d in Domain)
            cost += c.enforcement_per_check_unit * added
            complexity += int(added > 1e-12)
            dq = i.default_decision.threshold - b.default_decision.threshold
            cost += c.threshold_change_per_unit * max(0.0, dq)
            complexity += int(dq > 1e-12)
    for h in cfg.overlays:
        cost += c.overlay_per_cell_share * len(h.members) / n_cells
        complexity += 1
    return cost, complexity


def evaluate(state: SocialState, partition: Partition, cfg: Configuration, base: Configuration,
             rights: RightsThresholds, weights: dict[IntegChannel, float], manifest: ComposerManifest,
             salience: CausalAnswer, base_index: float) -> dict[str, Any]:
    dom = domination(state, partition, cfg.institutions, rights)
    frag = fragmentation(state, partition, cfg.overlays)
    integ = integration(state, partition, weights, cfg.overlays)
    pop_g = state.population.sum(axis=1).mean(axis=0)
    f_net = {f.group: f.value.mean for f in frag if f.channel is FragChannel.NETWORK and f.value is not None}
    index = institutionalization(state, partition, cfg)
    rri: list[float] | None = None
    if salience.known:
        iv = salience.interval()
        r = BoundedSalienceResponse(iv.lo, iv.hi, manifest.horizon_years, salience.reason).salience_response(
            index - base_index, manifest.horizon_years)
        assert r.lower is not None and r.upper is not None
        rri = [r.lower, r.upper]
    cost, complexity = _cost(cfg, base, manifest, len(partition.cell_ids))
    return {
        "violations": sum(int(d.violation) for d in dom),
        "max_p_exceed": max((d.p_exceed for d in dom), default=0.0),
        "violating": sorted({f"{d.group}|{d.level}|{d.domain.value}" for d in dom if d.violation}),
        "f_network": float(sum(f_net.get(g, 0.0) * pop_g[i] for i, g in enumerate(state.groups)) / pop_g.sum()),
        "j_conn": float(integ.j_conn.mean or 0.0) if integ.j_conn is not None else None,
        "institutionalization": index, "rri": rri, "cost": cost, "complexity": complexity,
    }


def border_cells(partition: Partition, adjacency: list[list[int]], ring: int) -> list[str]:
    """Cellules au contact d'une frontière d'État, étendues de ``ring`` anneaux."""
    top = partition.levels[0].assignment
    cells = {i for i, nb in enumerate(adjacency) if any(top[j] != top[i] for j in nb)}
    frontier = set(cells)
    for _ in range(ring):
        frontier = {j for i in frontier for j in adjacency[i]} - cells
        cells |= frontier
    return [partition.cell_ids[i] for i in sorted(cells)]


def _status(lo: dict[str, Any] | None, hi: dict[str, Any] | None, baseline_violations: int) -> str:
    if lo is None or hi is None:
        return "CAUSAL_EFFECT_UNKNOWN"
    if baseline_violations == 0:
        return "NOT_NEEDED" if lo["violations"] == 0 else "CREATES_VIOLATION"
    if lo["violations"] == 0:
        return "RESOLVES_ROBUSTLY"
    if hi["violations"] == 0:
        return "RESOLVES_POSSIBLY"
    return "DOES_NOT_RESOLVE"


_OBJECTIVES = ("max_p_exceed", "violations", "f_network", "j_conn", "rri_hi", "cost", "complexity")


def _objectives(m: dict[str, Any]) -> tuple[float, ...]:
    return tuple(float(m["rri"][1] if k == "rri_hi" and m["rri"] else 0.0 if k == "rri_hi" else
                       (m[k] if m[k] is not None else np.inf)) for k in _OBJECTIVES)


def compose(state: SocialState, partition: Partition, institutions: dict[str, list[Institution]],
            rights: RightsThresholds, weights: dict[IntegChannel, float], manifest: ComposerManifest,
            effects: dict[str, CausalAnswer], adjacency: list[list[int]],
            check_stop: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Évalue chaque levier seul, puis chaque préfixe de l'ordre de recherche, aux bornes de son effet."""
    base = Configuration({k: list(v) for k, v in institutions.items()}, [])
    salience = effects[manifest.salience_effect]
    base_index = institutionalization(state, partition, base)
    baseline = evaluate(state, partition, base, base, rights, weights, manifest, salience, base_index)
    cells = border_cells(partition, adjacency, manifest.overlay_ring)
    options: list[dict[str, Any]] = []
    deferred = [lv.lever.value for lv in manifest.levers if not lv.lever.fixed_geometry]
    fixed = [lv for lv in manifest.levers if lv.lever.fixed_geometry]

    def run(levers: list[LeverSpec], label: str) -> None:
        if check_stop is not None:
            check_stop(f"compose {label}")  # SIGTERM honoré entre deux options
        answers = [effects[lv.effect] for lv in levers if lv.effect]
        grades = sorted({a.grade.value for a in answers if a.grade is not None})
        if not all(a.known for a in answers):
            options.append({"option": label, "levers": [lv.lever.value for lv in levers], "lo": None, "hi": None,
                            "status": "CAUSAL_EFFECT_UNKNOWN", "grades": grades})
            return
        res = {}
        for bound in ("lo", "hi"):
            cfg = base
            for lv in levers:
                iv = effects[lv.effect].interval()  # type: ignore[index]
                cfg = apply_lever(cfg, lv, iv.lo if bound == "lo" else iv.hi, manifest, cells)
            res[bound] = evaluate(state, partition, cfg, base, rights, weights, manifest, salience, base_index)
        options.append({"option": label, "levers": [lv.lever.value for lv in levers], **res,
                        "status": _status(res["lo"], res["hi"], baseline["violations"]), "grades": grades})

    for lv in fixed:
        run([lv], lv.lever.value)
    for k in range(2, len(fixed) + 1):
        run(fixed[:k], f"cumul→{fixed[k - 1].lever.value}")

    if baseline["violations"] == 0:
        conclusion, chosen = "NO_CHANGE", None
    else:
        robust = [o for o in options if o["status"] == "RESOLVES_ROBUSTLY"]
        possible = [o for o in options if o["status"] == "RESOLVES_POSSIBLY"]
        if robust:
            conclusion, chosen = "NO_TERRITORIAL_CHANGE_SUFFICIENT", robust[0]["option"]
        elif possible:
            conclusion, chosen = "INSTITUTIONAL_UNCERTAIN", possible[0]["option"]
        else:
            conclusion, chosen = "INSTITUTIONAL_INSUFFICIENT_AT_FIXED_GEOMETRY", None
    # Ensemble non dominé (vue robuste, borne basse), baseline incluse : aucune option n'est « la » réponse.
    pool = [("status_quo", baseline)] + [(o["option"], o["lo"]) for o in options if o["lo"] is not None]
    front = [n for n, m in pool if not any(
        all(a <= b for a, b in zip(_objectives(m2), _objectives(m), strict=True))
        and any(a < b for a, b in zip(_objectives(m2), _objectives(m), strict=True)) for _, m2 in pool)]
    used = [o for o in options if o["option"] == chosen]
    evidence = "EXPLORATORY" if any("I7" in o["grades"] for o in used) or chosen is None else "CONDITIONAL"
    return {"baseline": baseline, "options": options, "conclusion": conclusion, "chosen": chosen,
            "evidence": evidence if conclusion != "NO_CHANGE" else "MODEL",
            "non_dominated": front, "objectives": list(_OBJECTIVES),
            "deferred_to_territorial_search": deferred, "overlay_cells": len(cells)}
