"""Provenance obligatoire (prompt §10).

Chaque transformation enregistre ``input_ids``, ``output_ids``, ``code_version``,
``parameters``, ``timestamp`` et ``run_id``. Le graphe ainsi formé permet de
remonter solution → métrique → champ latent → observations → sources.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from amtgo.errors import ProvenanceError
from amtgo.utils.canonical import stable_uuid
from amtgo.utils.code_version import code_version


def utcnow() -> datetime:
    return datetime.now(UTC)


class ProvenanceRecord(BaseModel):
    """Une transformation tracée. Son identifiant ne dépend que du contenu, pas de l'horloge."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: uuid.UUID
    transformation: str
    input_ids: tuple[str, ...]
    output_ids: tuple[str, ...]
    code_version: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    run_id: uuid.UUID | None = None
    timestamp: datetime = Field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        transformation: str,
        input_ids: Iterable[str],
        output_ids: Iterable[str],
        parameters: dict[str, Any] | None = None,
        run_id: uuid.UUID | None = None,
    ) -> ProvenanceRecord:
        ins = tuple(sorted(str(i) for i in input_ids))
        outs = tuple(sorted(str(o) for o in output_ids))
        if not outs:
            raise ProvenanceError(f"{transformation} : une transformation sans sortie n'a pas de sens")
        params = parameters or {}
        version = code_version()
        rid = stable_uuid(
            "provenance",
            {"t": transformation, "in": ins, "out": outs, "p": params, "code": version,
             "run": str(run_id) if run_id else None},
        )
        return cls(record_id=rid, transformation=transformation, input_ids=ins,
                   output_ids=outs, code_version=version, parameters=params, run_id=run_id)


class ProvenanceGraph:
    """Graphe de lignée en mémoire : vérifie qu'une sortie remonte à des sources."""

    def __init__(self, records: Iterable[ProvenanceRecord] = ()) -> None:
        self._by_output: dict[str, list[ProvenanceRecord]] = {}
        for r in records:
            self.add(r)

    def add(self, record: ProvenanceRecord) -> None:
        for out in record.output_ids:
            self._by_output.setdefault(out, []).append(record)

    def lineage(self, artifact_id: str) -> set[str]:
        """Tous les ancêtres de ``artifact_id`` (inclus)."""
        seen: set[str] = set()
        stack = [artifact_id]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            for rec in self._by_output.get(node, []):
                stack.extend(rec.input_ids)
        return seen

    def require_rooted(self, artifact_id: str, source_ids: set[str]) -> None:
        """Lève ProvenanceError si ``artifact_id`` ne remonte à aucune source connue."""
        if artifact_id not in self._by_output:
            raise ProvenanceError(f"aucune transformation ne produit {artifact_id}")
        if not (self.lineage(artifact_id) & source_ids):
            raise ProvenanceError(f"{artifact_id} ne remonte à aucune source enregistrée")
