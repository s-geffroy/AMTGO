"""M7 : bibliothèque causale gelée (schéma 10 §14).

Un effet est immuable dans une release : clé (effect_id, content_hash). Les
contraintes portent la doctrine : un effet I6/I7 ne porte que des bornes, et un
grade ne dépasse jamais le plafond de son design.

Revision ID: 0008
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE causal_effects (
            effect_id            uuid NOT NULL,
            content_hash         text NOT NULL CHECK (content_hash LIKE 'sha256:%'),
            effect_key           text NOT NULL,
            treatment_definition jsonb NOT NULL,
            outcome_definition   jsonb NOT NULL,
            estimand             text NOT NULL,
            source_context       text NOT NULL,
            target_context       text NOT NULL,
            design               text NOT NULL,
            identification_grade text NOT NULL CHECK (identification_grade IN
                                     ('I1', 'I2', 'I3', 'I4', 'I5', 'I6', 'I7')),
            effect_distribution  jsonb NOT NULL,
            time_horizon         jsonb NOT NULL,
            spillover_model      jsonb NOT NULL,
            transportability     text NOT NULL CHECK (transportability IN ('IDENTIFIED', 'PARTIAL', 'UNSUPPORTED')),
            overlap_score        double precision NOT NULL CHECK (overlap_score BETWEEN 0 AND 1),
            mechanism            jsonb NOT NULL,
            diagnostics          jsonb NOT NULL,
            frozen_release       text NOT NULL,
            PRIMARY KEY (effect_id, content_hash),
            CHECK (identification_grade NOT IN ('I6', 'I7')
                   OR effect_distribution->>'distribution_type' <> 'EMPIRICAL'),
            CHECK (design <> 'expert_hypothesis' OR identification_grade = 'I7')
        )""")
    op.execute("""
        CREATE TABLE causal_freezes (
            run_id      uuid NOT NULL REFERENCES run_manifests (run_id),
            freeze_hash text NOT NULL CHECK (freeze_hash LIKE 'sha256:%'),
            effect_id   uuid NOT NULL,
            content_hash text NOT NULL,
            PRIMARY KEY (run_id, effect_id),
            FOREIGN KEY (effect_id, content_hash) REFERENCES causal_effects (effect_id, content_hash)
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE causal_freezes")
    op.execute("DROP TABLE causal_effects")
