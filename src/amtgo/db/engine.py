"""Connexion à la base dédiée et migrations Alembic versionnées."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine

from amtgo.config.settings import Settings
from amtgo.db.repository import NullRepository, PostgresRepository, Repository

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def make_engine(settings: Settings) -> Engine:
    return create_engine(settings.database_url(), pool_pre_ping=True, future=True)


def make_repository(settings: Settings) -> Repository:
    if not settings.db_enabled:
        return NullRepository()
    return PostgresRepository(make_engine(settings))


def alembic_config(settings: Settings):  # type: ignore[no-untyped-def]
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # '%' doublé : ConfigParser interprète les interpolations.
    cfg.set_main_option("sqlalchemy.url", settings.database_url().replace("%", "%%"))
    return cfg


def upgrade(settings: Settings, revision: str = "head") -> None:
    from alembic import command

    command.upgrade(alembic_config(settings), revision)


def current_revision(settings: Settings) -> str | None:
    from alembic.runtime.migration import MigrationContext

    with make_engine(settings).connect() as cx:
        return MigrationContext.configure(cx).get_current_revision()
