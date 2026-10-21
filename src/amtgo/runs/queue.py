"""File de runs du worker (ADR-0012).

``submit`` gèle une requête en RunManifest et crée ``/state/runs/<run_id>/``.
``advance_one`` exécute **une** étape du plus ancien run non terminé et écrit
l'état aussitôt. Le worker l'appelle à chaque cycle : un redémarrage, un SIGTERM
ou un plantage ne perdent au plus que l'étape en cours, rejouée au cycle suivant.

Échecs :
- erreur AMTGO (licence, privacy, topologie, configuration…) : déterministe,
  rejouer ne changerait rien → run FAILED immédiatement, message conservé ;
- autre exception (réseau, base, disque) : transitoire → nouvelle tentative au
  cycle suivant, FAILED après ``max_stage_attempts``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from amtgo.config.loader import load_model
from amtgo.config.settings import Settings
from amtgo.core.provenance import utcnow
from amtgo.db.repository import Repository
from amtgo.errors import AMTGOError, StageInterrupted
from amtgo.manifests.continental import ContinentalManifest, ContinentalRequest, is_continental, resolve_continental
from amtgo.manifests.run import RunManifest, RunRequest, resolve_request
from amtgo.runs import continental_stages
from amtgo.runs.stages import StageContext, plan_steps, run_step
from amtgo.runs.state import RunState, RunStatus, StepState, load_state, save_state, write_json_atomic
from amtgo.utils.logging import log_event


def runs_dir(settings: Settings) -> Path:
    return settings.state_dir / "runs"


def cache_dir(settings: Settings) -> Path:
    return settings.state_dir / "cache"


AnyManifest = RunManifest | ContinentalManifest


def submit(request_path: Path, settings: Settings) -> tuple[AnyManifest, bool]:
    """Soumet une requête. Renvoie (manifeste, créé?) ; resoumettre le même contenu est sans effet.

    Une requête continentale (M14) soumet d'abord ses runs régionaux : le worker suivant
    l'ordre de soumission, la composition ne démarre qu'après eux.
    """
    manifest: AnyManifest
    if is_continental(request_path):
        crequest = load_model(ContinentalRequest, request_path)
        manifest, regional = resolve_continental(crequest, settings.configs_dir)
        for path in regional.values():
            submit(path, settings)
        name, steps = crequest.name, continental_stages.plan_steps(manifest)
    else:
        request = load_model(RunRequest, request_path)
        manifest = resolve_request(request, settings.configs_dir)
        name, steps = request.name, plan_steps(manifest)
    run_dir = runs_dir(settings) / str(manifest.run_id)
    if (run_dir / "state.json").exists():
        return load_manifest(run_dir), False
    write_json_atomic(run_dir / "manifest.json", manifest.model_dump_json(indent=2))
    state = RunState(run_id=str(manifest.run_id), steps=[StepState(name=s) for s in steps])
    save_state(run_dir, state)
    log_event("run.submitted", run_id=str(manifest.run_id), count=len(state.steps), detail=name)
    return manifest, True


def load_manifest(run_dir: Path) -> AnyManifest:
    text = (run_dir / "manifest.json").read_text(encoding="utf-8")
    if '"kind": "continental"' in text[:200] or '"kind":"continental"' in text[:200]:
        return ContinentalManifest.model_validate_json(text)
    return RunManifest.model_validate_json(text)


def list_runs(settings: Settings) -> list[RunState]:
    root = runs_dir(settings)
    if not root.exists():
        return []
    states = [load_state(d) for d in root.iterdir() if (d / "state.json").exists()]
    return sorted(states, key=lambda s: (s.submitted_at, s.run_id))


def _next_run(settings: Settings) -> RunState | None:
    return next((s for s in list_runs(settings) if not s.status.terminal), None)


@dataclass(frozen=True)
class Advance:
    run_id: str
    step: str
    status: RunStatus
    outcome: str  # done | interrupted | retry | failed


def advance_one(
    settings: Settings,
    repo: Repository,
    should_stop: Callable[[], bool] = lambda: False,
    run_id: str | None = None,
) -> Advance | None:
    """Une étape du plus ancien run non terminé (ou de ``run_id`` s'il est donné)."""
    if run_id is None:
        state = _next_run(settings)
    else:
        state = load_state(runs_dir(settings) / run_id)
        if state.status.terminal:
            return None
    if state is None:
        return None
    run_dir = runs_dir(settings) / state.run_id
    step = state.next_step()
    if step is None:  # cohérence : toutes les étapes faites mais statut non terminal
        state.status = RunStatus.SUCCEEDED
        save_state(run_dir, state)
        return Advance(state.run_id, "-", state.status, "done")

    manifest = load_manifest(run_dir)
    run: Callable[[], dict[str, Any]]
    if isinstance(manifest, ContinentalManifest):
        cctx = continental_stages.ContinentalContext(run_dir, manifest, repo, runs_dir(settings), cache_dir(settings),
                                                     should_stop)
        run = lambda: continental_stages.run_step(cctx, step.name)  # noqa: E731
    else:
        ctx = StageContext(run_dir, manifest, repo, cache_dir(settings), should_stop)
        run = lambda: run_step(ctx, step.name)  # noqa: E731
    state.status = RunStatus.RUNNING
    step.started_at = utcnow()
    step.attempts += 1
    save_state(run_dir, state)

    t0 = time.monotonic()
    try:
        info = run()
    except StageInterrupted:
        step.attempts -= 1  # un arrêt demandé n'est pas un échec
        save_state(run_dir, state)
        log_event("run.step", run_id=state.run_id, stage=step.name, status="interrupted")
        return Advance(state.run_id, step.name, state.status, "interrupted")
    except AMTGOError as exc:
        return _fail(run_dir, state, step, exc, time.monotonic() - t0, deterministic=True,
                     settings=settings)
    except Exception as exc:  # transitoire présumé : réessayé, jamais avalé
        return _fail(run_dir, state, step, exc, time.monotonic() - t0, deterministic=False,
                     settings=settings)

    step.done = True
    step.last_error = None
    step.finished_at = utcnow()
    step.duration_s = round(time.monotonic() - t0, 3)
    if state.next_step() is None:
        state.status = RunStatus.SUCCEEDED
    save_state(run_dir, state)
    log_event("run.step", run_id=state.run_id, stage=step.name, status="done",
              duration_s=step.duration_s, **{k: v for k, v in info.items() if k in ("count", "detail")})
    if state.status is RunStatus.SUCCEEDED:
        log_event("run.succeeded", run_id=state.run_id, path=str(run_dir / "report.md"))
    return Advance(state.run_id, step.name, state.status, "done")


# Longueur maximale d'un message d'erreur journalisé ou stocké dans l'état.
MAX_ERROR_CHARS = 500


def safe_error(exc: BaseException) -> str:
    """Message d'erreur sans donnée : pas de paramètres SQL liés, longueur bornée.

    Une erreur SQLAlchemy recopie toutes les valeurs liées (observations, comptes) :
    elle ne doit jamais atteindre les logs ni l'état du run (CLAUDE.md, prompt §70).
    """
    from sqlalchemy.exc import StatementError

    if isinstance(exc, StatementError) and exc.orig is not None:
        text = f"{type(exc).__name__}: {type(exc.orig).__name__}: {str(exc.orig).splitlines()[0]}"
    else:
        text = f"{type(exc).__name__}: {exc}"
    return text if len(text) <= MAX_ERROR_CHARS else text[: MAX_ERROR_CHARS - 1] + "…"


def _fail(run_dir: Path, state: RunState, step: StepState, exc: BaseException, elapsed: float,
          *, deterministic: bool, settings: Settings) -> Advance:
    message = safe_error(exc)
    step.last_error = message
    step.duration_s = round(elapsed, 3)
    exhausted = step.attempts >= settings.max_stage_attempts
    if deterministic or exhausted:
        state.status = RunStatus.FAILED
        state.error = f"{step.name}: {message}"
        outcome = "failed"
    else:
        outcome = "retry"
    save_state(run_dir, state)
    log_event("run.step", run_id=state.run_id, stage=step.name, status=outcome,
              attempt=step.attempts, error=message)
    return Advance(state.run_id, step.name, state.status, outcome)


def run_to_completion(settings: Settings, repo: Repository, run_id: str) -> RunState:
    """Exécution synchrone d'un run (CLI, CI) : mêmes étapes, même code que le worker.

    Un run continental exécute d'abord ses runs régionaux, comme le ferait le worker.
    """
    manifest = load_manifest(runs_dir(settings) / run_id)
    if isinstance(manifest, ContinentalManifest):
        for rr in manifest.regions:
            run_to_completion(settings, repo, str(rr.run_id))
    while advance_one(settings, repo, run_id=run_id) is not None:
        pass
    return load_state(runs_dir(settings) / run_id)
