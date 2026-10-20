"""Logs structurés : une ligne JSON par événement, sur stdout, non bufferisée.

Champs normalisés (prompt §70) : ``run_id``, ``stage``, ``dataset_id``,
``territory_id``, ``scenario_id``, ``duration_s``, ``status``. Aucune PII : on
journalise des identifiants et des comptes, jamais des valeurs d'observation.

Le volume de logs est une ressource : journaliser les étapes et les erreurs, pas
chaque itération d'une boucle interne.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

_ALLOWED_EXTRA = {
    "run_id",
    "stage",
    "dataset_id",
    "source_id",
    "mesh_id",
    "territory_id",
    "scenario_id",
    "duration_s",
    "status",
    "count",
    "attempt",
    "error",
    "detail",
    "path",
}


def log_event(event: str, **fields: Any) -> None:
    """Écrit ``{"ts":..., "event":..., ...}`` sur stdout et flush.

    Les clés hors liste blanche sont refusées : c'est le garde-fou le plus
    simple contre une fuite de donnée dans les logs.
    """
    unknown = set(fields) - _ALLOWED_EXTRA
    if unknown:
        raise ValueError(f"champs de log non autorisés : {sorted(unknown)}")
    record: dict[str, Any] = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event}
    record.update({k: v for k, v in fields.items() if v is not None})
    print(json.dumps(record, ensure_ascii=False, default=str), file=sys.stdout, flush=True)
