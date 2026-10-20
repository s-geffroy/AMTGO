"""Intégration PostGIS : migrations et persistance idempotente (marqueur ``db``)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from amtgo.config.settings import Settings

pytestmark = pytest.mark.db

if not os.environ.get("AMTGO_DB_HOST"):
    pytest.skip("AMTGO_DB_HOST absent : base non disponible", allow_module_level=True)


@pytest.fixture
def db_settings(settings: Settings) -> Settings:
    env = Settings()
    return settings.model_copy(update={k: getattr(env, k) for k in
                                       ("db_host", "db_port", "db_name", "db_user", "db_password_file")})


def test_migrations_and_persistence(db_settings: Settings) -> None:
    from amtgo.db.engine import current_revision, make_engine, make_repository, upgrade
    from amtgo.runs.queue import run_to_completion, submit
    from amtgo.runs.state import RunStatus

    upgrade(db_settings)
    assert current_revision(db_settings) == "0004"
    repo = make_repository(db_settings)
    manifest, _ = submit(db_settings.configs_dir / "runs/synthetic_pilot.yaml", db_settings)
    state = run_to_completion(db_settings, repo, str(manifest.run_id))
    assert state.status is RunStatus.SUCCEEDED, state.error

    engine = make_engine(db_settings)
    with engine.connect() as cx:
        def count(sql: str) -> int:
            return int(cx.execute(text(sql), {"r": manifest.run_id}).scalar_one())

        assert count("SELECT count(*) FROM run_manifests WHERE run_id = :r") == 1
        n_obs = count("SELECT count(*) FROM observations o JOIN sources s USING (source_id) "
                      "WHERE s.slug = 'synthetic_pilot' AND :r IS NOT NULL")
        assert n_obs == 200
        assert count("SELECT count(*) FROM provenance_records WHERE run_id = :r") >= 6
        assert count("SELECT count(*) FROM cells WHERE mesh_id = 'pilot_grid_l4' AND :r IS NOT NULL") > 0
        bad = count("SELECT count(*) FROM cells WHERE NOT ST_IsValid(geometry) AND :r IS NOT NULL")
        assert bad == 0

    # Rejouer toutes les écritures ne duplique rien.
    from amtgo.data.ingestion import read_observations
    from amtgo.runs.queue import runs_dir

    path = runs_dir(db_settings) / str(manifest.run_id) / "artifacts" / "observations__synthetic_pilot.parquet"
    repo.record_observations(read_observations(path))
    with engine.connect() as cx:
        n = cx.execute(text("SELECT count(*) FROM observations o JOIN sources s USING (source_id) "
                            "WHERE s.slug = 'synthetic_pilot'")).scalar_one()
        assert n == 200


def test_check_constraints(db_settings: Settings) -> None:
    from sqlalchemy.exc import IntegrityError

    from amtgo.db.engine import make_engine, upgrade

    upgrade(db_settings)
    engine = make_engine(db_settings)
    with pytest.raises(IntegrityError), engine.begin() as cx:
        cx.execute(text("""
            INSERT INTO mesh_definitions (mesh_id, definition_hash, family, resolution, definition,
                cells_hash, cell_count)
            VALUES ('x', 'h', 'hexagonal_magic', 1, '{}', 'h', 1)"""))
