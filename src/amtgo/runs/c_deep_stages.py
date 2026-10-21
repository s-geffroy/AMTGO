"""Étapes d'un run Map-C-Deep (branche de recherche, 11 phase 11). Bornées, idempotentes, reprenables.

``history`` → ``estimate:<modèle>`` … → ``bootstrap:<modèle>`` … → ``counterfactual`` → ``report``.

``history`` génère l'histoire du monde synthétique et sépare deux artefacts : les
observations (seules lues par l'estimation) et la vérité (lue seulement par la
calibration). Aucune étape n'écrit en base : un contre-factuel historique n'est pas
un produit (aucune archive, aucune solution, aucune carte).
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from amtgo.core.provenance import ProvenanceRecord
from amtgo.errors import ConfigurationError, StageInterrupted
from amtgo.manifests.c_deep import STATUS, CDeepManifest, verify_c_deep
from amtgo.research import c_deep as cd
from amtgo.research import historical_scm as h
from amtgo.runs import artifacts
from amtgo.runs.state import write_json_atomic
from amtgo.utils.canonical import content_hash

OBS = "artifacts/historical_observations.npz"


@dataclass
class CDeepContext:
    run_dir: Path
    manifest: CDeepManifest
    should_stop: Callable[[], bool]

    def check_stop(self, what: str = "c_deep") -> None:
        if self.should_stop():
            raise StageInterrupted(what)


def plan_steps(m: CDeepManifest) -> list[str]:
    models = [x.value for x in m.request.models]
    return ["history", *[f"estimate:{x}" for x in models], *[f"bootstrap:{x}" for x in models],
            "counterfactual", "report"]


def _save_obs(run_dir: Path, obs: h.Observations) -> None:
    arrays: dict[str, np.ndarray] = {"start": np.array(obs.start), "init_cells": obs.init_cells}
    for name in ("census", "shares", "survey"):
        for y, v in getattr(obs, name).items():
            arrays[f"{name}__{y}"] = v
    for k, v in obs.noise.items():
        arrays[f"noise__{k}"] = np.array(v)
    buf = io.BytesIO()
    np.savez(buf, **arrays)  # type: ignore[arg-type]
    artifacts.write_bytes(run_dir, OBS, buf.getvalue())


def _load_obs(run_dir: Path) -> h.Observations:
    data = np.load(io.BytesIO((run_dir / OBS).read_bytes()))
    by: dict[str, dict[int, np.ndarray]] = {"census": {}, "shares": {}, "survey": {}}
    noise = {}
    for key in data.files:
        name, _, rest = key.partition("__")
        if name in by:
            by[name][int(rest)] = data[key]
        elif name == "noise":
            noise[rest] = float(data[key])
    return h.Observations(int(data["start"]), data["init_cells"], by["census"], by["shares"], by["survey"], noise)


def history_stage(ctx: CDeepContext, _: str) -> dict[str, Any]:
    verify_c_deep(ctx.manifest)
    obs, truth = cd.generate(ctx.manifest.request)
    _save_obs(ctx.run_dir, obs)
    artifacts.write_json(ctx.run_dir, "artifacts/synthetic_truth.json",
                         {"use": "calibration seulement — jamais lue par l'estimation", **truth})
    return {"count": len(obs.census), "detail": f"recensements={len(obs.census)} enquêtes={len(obs.survey)}"}


def estimate_stage(ctx: CDeepContext, model: str) -> dict[str, Any]:
    req = ctx.manifest.request
    obs = _load_obs(ctx.run_dir)
    try:
        est = cd.estimate(req, obs, h.Model(model), should_stop=lambda: ctx.check_stop(f"estimate {model}"))
    except ValueError as exc:  # données historiques insuffisantes : non identifiable, jamais un défaut avalé
        est = {"model": model, "gate_h": False, "reason": str(exc), "checks": {}}
    artifacts.write_json(ctx.run_dir, f"artifacts/scm__{model}.json", est)
    failed = [k for k, c in est["checks"].items() if not c["passed"]]
    return {"detail": f"gate_H={'PASSED' if est['gate_h'] else 'FAILED'}"
                      + (f" ({', '.join(failed) or est.get('reason', '')})" if not est["gate_h"] else "")}


def bootstrap_stage(ctx: CDeepContext, model: str) -> dict[str, Any]:
    est = artifacts.read_json(ctx.run_dir, f"artifacts/scm__{model}.json")
    if not est["gate_h"]:
        artifacts.write_json(ctx.run_dir, f"artifacts/bootstrap__{model}.json", {"draws": [], "skipped": True})
        return {"count": 0, "detail": "modèle non validé : hors ensemble"}
    draws = cd.ensemble_draws(ctx.manifest.request, _load_obs(ctx.run_dir), est,
                              should_stop=lambda: ctx.check_stop(f"bootstrap {model}"))
    artifacts.write_json(ctx.run_dir, f"artifacts/bootstrap__{model}.json", {"draws": draws, "skipped": False})
    return {"count": len(draws)}


def counterfactual_stage(ctx: CDeepContext, _: str) -> dict[str, Any]:
    req = ctx.manifest.request
    models = [x.value for x in req.models]
    ests = {m: artifacts.read_json(ctx.run_dir, f"artifacts/scm__{m}.json") for m in models}
    draws = {m: artifacts.read_json(ctx.run_dir, f"artifacts/bootstrap__{m}.json")["draws"] for m in models}
    ensemble = [m for m in models if ests[m]["gate_h"] and draws[m]]
    product: dict[str, Any] = {
        "status": STATUS, "experimental": True, "branch": "research (11 phase 11) — hors produit principal",
        "question": "comment les sociétés auraient-elles pu évoluer sous une autre histoire institutionnelle ? "
                    "(08 §19)",
        "gate_h": {m: {"passed": e["gate_h"], "checks": e["checks"], "reason": e.get("reason")}
                   for m, e in ests.items()},
        "ensemble": ensemble, "theta": {m: {"estimate": ests[m].get("theta"), "se": ests[m].get("se")}
                                        for m in models},
        "contemporary_coefficients": "aucun : SCM estimé sur l'histoire observée seulement (04 §20)",
        "counterfactual_actions": "frontières et capitales seulement ; aucun déplacement de population",
        "public_layer": {"published": False, "features": [], "reason": "contre-factuel historique : jamais une carte"},
        "valid_as_of": {"run_created_at": ctx.manifest.created_at.isoformat(),
                        "history": [req.history.start, req.history.end]},
        "privacy_class": "CONTROLLED"}
    if len(ensemble) < req.validation.min_structural_forms:
        product.update({"conclusion": "NOT_IDENTIFIABLE", "counterfactual": None, "reason": (
            f"{len(ensemble)} forme(s) structurelle(s) passe(nt) la validation historique (Gate H), "
            f"{req.validation.min_structural_forms} exigées : une validation factuelle ne valide pas un "
            "contre-factuel, l'incertitude structurelle doit rester représentée")})
    else:
        truth = artifacts.read_json(ctx.run_dir, "artifacts/synthetic_truth.json")
        res = cd.counterfactual(req, _load_obs(ctx.run_dir), {m: draws[m] for m in ensemble}, truth)
        groups = {kind: {k: v for k, v in res[kind].items() if k.startswith("group_share_")}
                  for kind in ("factual", "counterfactual", "delta")}
        public = {kind: {k: res[kind][k] for k in cd.INDICATORS} for kind in ("factual", "counterfactual", "delta")}
        cal = res.get("calibration", {})
        calibrated = bool(cal) and all(c["counterfactual_covered"] and c["delta_covered"] for c in cal.values())
        product.update({
            "conclusion": "HISTORICAL_COUNTERFACTUAL_ESTIMATED", "counterfactual": public, "n_draws": res["n_draws"],
            "calibration": {"on_synthetic_truth": cal, "status": "COVERED" if calibrated else "NOT_COVERED"},
            "interval_level": req.validation.interval_level})
        artifacts.write_json(ctx.run_dir, "artifacts/c_deep_groups.json",
                             {"privacy_class": "CONTROLLED", "export": "jamais public (parts de groupes)", **groups})
    artifacts.write_json(ctx.run_dir, "artifacts/c_deep.json", product)
    artifacts.write_provenance(ctx.run_dir, [ProvenanceRecord.create(
        "research.c_deep", [f"historical_observations:{content_hash(product['gate_h'])}"],
        [f"c_deep:{content_hash(product)}"], run_id=ctx.manifest.run_id)])
    return {"count": len(ensemble), "detail": f"{product['conclusion']} ensemble={'+'.join(ensemble) or '∅'}"
                                              + (f" calibration={product['calibration']['status']}"
                                                 if ensemble else "")}


def report_stage(ctx: CDeepContext, _: str) -> dict[str, Any]:
    from amtgo.runs.report import render_c_deep

    product = artifacts.read_json(ctx.run_dir, "artifacts/c_deep.json")
    write_json_atomic(ctx.run_dir / "report.md", render_c_deep(ctx.manifest, product))
    return {"detail": product["conclusion"]}


STAGES: dict[str, Callable[[CDeepContext, str], dict[str, Any]]] = {
    "history": history_stage, "estimate": estimate_stage, "bootstrap": bootstrap_stage,
    "counterfactual": counterfactual_stage, "report": report_stage}


def run_step(ctx: CDeepContext, name: str) -> dict[str, Any]:
    stage, _, arg = name.partition(":")
    fn = STAGES.get(stage)
    if fn is None:
        raise ConfigurationError(f"étape Map-C-Deep inconnue : {name}")
    return fn(ctx, arg)
