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
    assert current_revision(db_settings) == "0012"
    repo = make_repository(db_settings)
    manifest, _ = submit(db_settings.configs_dir / "runs/synthetic_pilot.yaml", db_settings)
    state = run_to_completion(db_settings, repo, str(manifest.run_id))
    assert state.status is RunStatus.SUCCEEDED, state.error

    engine = make_engine(db_settings)
    with engine.connect() as cx:
        def count(sql: str) -> int:
            return int(cx.execute(text(sql), {"r": manifest.run_id}).scalar_one())

        assert count("SELECT count(*) FROM run_manifests WHERE run_id = :r") == 1
        survey = next(x.manifest for x in manifest.data_manifest if x.manifest.source_id == "synthetic_survey")
        n_obs = int(cx.execute(text("SELECT count(*) FROM observations WHERE source_id = :s "
                                    "AND variable_id = 'population_count_ea'"),
                               {"s": survey.source_uuid}).scalar_one())
        assert n_obs == 300
        assert count("SELECT count(*) FROM provenance_records WHERE run_id = :r") >= 6
        assert count("SELECT count(*) FROM cells WHERE mesh_id = 'pilot_grid_l4' AND :r IS NOT NULL") > 0
        bad = count("SELECT count(*) FROM cells WHERE NOT ST_IsValid(geometry) AND :r IS NOT NULL")
        assert bad == 0
        # M3 : un champ par maillage, toutes cellules résumées, statut MODEL, gel enregistré.
        assert count("SELECT count(*) FROM latent_fields WHERE run_id = :r") == 4
        assert count("SELECT count(*) FROM latent_field_cells c JOIN latent_fields f USING (field_id) "
                     "WHERE f.run_id = :r AND f.mesh_id = 'pilot_grid_l4'") == count(
            "SELECT count(*) FROM cells WHERE mesh_id = 'pilot_grid_l4' AND :r IS NOT NULL")
        assert count("SELECT count(*) FROM latent_fields WHERE run_id = :r AND evidence_status <> 'M'") == 0
        assert count("SELECT count(*) FROM run_manifests WHERE run_id = :r AND measurement_hash LIKE 'sha256:%'") == 1
        # M4 : registre des ontologies et des crosswalks, sans table « ethnicity ».
        assert count("SELECT count(DISTINCT ontology_id) FROM ontologies WHERE :r IS NOT NULL") >= 2
        assert count("SELECT count(*) FROM ontology_crosswalk WHERE :r IS NOT NULL") > 0
        assert count("SELECT count(*) FROM information_schema.tables "
                     "WHERE table_name ILIKE '%ethnic%' AND :r IS NOT NULL") == 0
        # M6 : régimes de la sensibilité et scénarios enregistrés, garde-fous en contraintes.
        assert count("SELECT count(DISTINCT regime_id) FROM constitutional_regimes WHERE :r IS NOT NULL") == 4
        assert count("SELECT count(DISTINCT scenario_id) FROM scenarios WHERE :r IS NOT NULL") == 4
        # M7 : bibliothèque gelée enregistrée et rattachée au run.
        assert count("SELECT count(*) FROM causal_freezes WHERE run_id = :r") == 10
        assert count("SELECT count(*) FROM run_manifests WHERE run_id = :r "
                     "AND causal_library_hash LIKE 'sha256:%'") == 1
        # M8 : territoires candidats enregistrés, valides, jamais actifs.
        assert count("SELECT count(*) FROM territory_candidates WHERE run_id = :r") > 0
        assert count("SELECT count(*) FROM territory_candidates WHERE run_id = :r AND active") == 0
        # M10 : archive enregistrée, aucune solution autre que NOT_IDENTIFIABLE.
        assert count("SELECT count(*) FROM solutions WHERE run_id = :r") == 15
        assert count("SELECT count(*) FROM solutions WHERE run_id = :r AND status <> 'NOT_IDENTIFIABLE'") == 0
        # M11 : un gate par lettre ; aucune solution ROBUST/CONDITIONAL sans eux (déclencheur).
        assert count("SELECT count(*) FROM validation_gates WHERE run_id = :r") == 5
        assert count("SELECT count(*) FROM solutions WHERE run_id = :r AND stability ? 'validated'") == 15

    # M11 : la base refuse une solution « ROBUST » quand un gate du run n'est pas passé.
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="sans tous les gates"), engine.begin() as cx:
        cx.execute(text("UPDATE solutions SET status = 'ROBUST' WHERE run_id = :r"), {"r": manifest.run_id})

    # Rejouer toutes les écritures ne duplique rien.
    from amtgo.data.ingestion import read_observations
    from amtgo.runs.queue import runs_dir

    path = runs_dir(db_settings) / str(manifest.run_id) / "artifacts" / "observations__synthetic_survey.parquet"
    repo.record_observations(read_observations(path))
    with engine.connect() as cx:
        n = cx.execute(text("SELECT count(*) FROM observations WHERE source_id = :s "
                            "AND variable_id = 'population_count_ea'"), {"s": survey.source_uuid}).scalar_one()
        assert n == 300


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
    with pytest.raises(IntegrityError), engine.begin() as cx:
        # Un scénario portant un déplacement forcé ne peut pas être enregistré (prompt §86).
        cx.execute(text("""
            INSERT INTO scenarios (scenario_id, content_hash, version, mobility_regime, horizon_years,
                population, climate, urbanization, economy, migration, infrastructure, security)
            VALUES ('x', 'sha256:x', '1', 'S1', 10, '{}', '{}', '{}', '{}',
                '{"forced_migration": 1000, "reform_induced_relocation": 0}', '{}', '{}')"""))
    with pytest.raises(IntegrityError), engine.begin() as cx:
        # Une hypothèse d'expert (I7) ne porte jamais une loi d'effet (04 §5).
        cx.execute(text("""
            INSERT INTO causal_effects (effect_id, content_hash, effect_key, treatment_definition,
                outcome_definition, estimand, source_context, target_context, design, identification_grade,
                effect_distribution, time_horizon, spillover_model, transportability, overlap_score,
                mechanism, diagnostics, frozen_release)
            VALUES (gen_random_uuid(), 'sha256:x', 'x', '{}', '{}', 'ATT', 's', 't', 'expert_hypothesis', 'I7',
                '{"distribution_type": "EMPIRICAL"}', '{}', '{}', 'IDENTIFIED', 1.0, '{}', '{}', 'r')"""))
