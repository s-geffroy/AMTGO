"""Version du code, reportée dans chaque provenance et chaque RunManifest.

Deux composantes : ``AMTGO_CODE_COMMIT`` (commit git, injecté au build quand il
est connu) et l'empreinte du code source du paquet, calculée au premier appel.
La seconde suffit à la reproductibilité même quand le commit est inconnu.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def source_tree_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        h.update(path.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]


def code_commit() -> str:
    return os.environ.get("AMTGO_CODE_COMMIT", "unknown") or "unknown"


def code_version() -> str:
    return f"{code_commit()}+src.{source_tree_hash()}"
