"""Réglages d'exécution (pydantic-settings).

Uniquement de l'infrastructure : chemins, base, intervalle. Aucun paramètre
normatif ici — ceux-là vivent dans un NormativeManifest versionné (prompt §59).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AMTGO_", extra="ignore")

    state_dir: Path = Path("/state")
    configs_dir: Path = Path("/app/configs")

    db_host: str | None = None
    db_port: int = 5432
    db_name: str = "amtgo"
    db_user: str = "amtgo"
    db_password_file: Path | None = None

    # Tentatives d'une étape de run avant passage en FAILED.
    max_stage_attempts: int = Field(default=3, ge=1)

    @property
    def db_enabled(self) -> bool:
        return bool(self.db_host)

    def database_url(self) -> str:
        """URL SQLAlchemy. Le mot de passe est lu dans le secret, jamais dans l'environnement."""
        if not self.db_host:
            raise RuntimeError("base désactivée : AMTGO_DB_HOST absent")
        password = ""
        if self.db_password_file is not None:
            password = self.db_password_file.read_text().strip()
        from urllib.parse import quote

        auth = self.db_user + (":" + quote(password, safe="") if password else "")
        return f"postgresql+psycopg://{auth}@{self.db_host}:{self.db_port}/{self.db_name}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
