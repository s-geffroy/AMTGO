"""État persistant d'un run, écrit atomiquement dans ``/state/runs/<run_id>/state.json``.

Le run est une liste ordonnée d'étapes. Une étape n'est marquée ``done`` qu'une
fois ses sorties écrites : une interruption à n'importe quel moment laisse un
état cohérent, et l'étape est simplement rejouée (ses écritures sont
idempotentes).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from amtgo.core.provenance import utcnow


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"

    @property
    def terminal(self) -> bool:
        return self in (RunStatus.SUCCEEDED, RunStatus.FAILED)


class StepState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    done: bool = False
    attempts: int = 0
    last_error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_s: float | None = None


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus = RunStatus.PENDING
    submitted_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    steps: list[StepState]
    error: str | None = None

    def next_step(self) -> StepState | None:
        return next((s for s in self.steps if not s.done), None)


def write_json_atomic(path: Path, text: str) -> None:
    """Écrit ``text`` dans ``path`` via un fichier temporaire, fsync, puis rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)


def save_state(run_dir: Path, state: RunState) -> None:
    state.updated_at = utcnow()
    write_json_atomic(run_dir / "state.json", state.model_dump_json(indent=2))


def load_state(run_dir: Path) -> RunState:
    return RunState.model_validate(json.loads((run_dir / "state.json").read_text(encoding="utf-8")))
