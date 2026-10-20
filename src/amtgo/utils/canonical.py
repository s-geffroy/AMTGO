"""Sérialisation canonique et empreintes.

Toute identité stable (run_id, mesh hash, content hash d'un enregistrement) passe
par ici : JSON trié, sans espace, flottants en repr, puis sha256. Deux objets
égaux donnent la même empreinte sur toute machine.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Espace de noms des UUID5 d'AMTGO. Constante d'identité, pas paramètre normatif :
# la changer changerait tous les identifiants stables.
AMTGO_NAMESPACE = uuid.UUID("6f1c2a52-6d43-5b8e-9a51-0a4e1d2c7b30")


def _normalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"valeur non finie non sérialisable canoniquement : {value!r}")
        return value
    if hasattr(value, "model_dump"):
        return _normalize(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, set | frozenset):
        return sorted(_normalize(v) for v in value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_normalize(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    """JSON canonique : clés triées, séparateurs compacts, UTF-8."""
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_hash(value: Any) -> str:
    """Empreinte ``sha256:<hex>`` du contenu canonique."""
    return "sha256:" + sha256_hex(canonical_json(value))


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return "sha256:" + h.hexdigest()


def stable_uuid(kind: str, payload: Any) -> uuid.UUID:
    """UUID5 déterministe pour un objet de type ``kind`` au contenu ``payload``."""
    return uuid.uuid5(AMTGO_NAMESPACE, f"{kind}:{canonical_json(payload)}")
