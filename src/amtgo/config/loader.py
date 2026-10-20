"""Chargement YAML typé, avec empreinte du contenu chargé."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from amtgo.errors import ConfigurationError


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"fichier introuvable : {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"YAML invalide dans {path} : {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"{path} : un mapping YAML est attendu")
    return data


def load_model[M: BaseModel](model: type[M], path: Path) -> M:
    try:
        return model.model_validate(read_yaml(path))
    except ValidationError as exc:
        raise ConfigurationError(f"{path} : {exc}") from exc
