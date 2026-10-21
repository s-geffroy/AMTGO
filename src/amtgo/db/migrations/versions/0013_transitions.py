"""M12 : trajectoires de transition Map-R (schéma 10 §19).

Une ligne par étape de trajectoire, rattachée à la solution visée (statu quo,
réforme institutionnelle ou variante territoriale) de l'archive du run. Les
types d'action suivent la hiérarchie contrefactuelle du prompt §79.

Revision ID: 0013
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TYPE transition_action AS ENUM ('no_change', 'rights_enforcement', 'institutional_reform',
            'autonomy', 'federation', 'border_weakening', 'border_change', 'sovereignty')""")
    op.execute("""
        CREATE TABLE transitions (
            transition_id        uuid PRIMARY KEY,
            run_id               uuid NOT NULL REFERENCES run_manifests (run_id),
            solution_id          uuid NOT NULL REFERENCES solutions (solution_id),
            path_id              text NOT NULL,
            step                 integer NOT NULL CHECK (step >= 1),
            action_type          transition_action NOT NULL,
            action_payload       jsonb NOT NULL,
            cost_distribution    jsonb NOT NULL,
            irreversibility      double precision NOT NULL CHECK (irreversibility BETWEEN 0 AND 1),
            value_of_information double precision NOT NULL CHECK (value_of_information BETWEEN 0 AND 1),
            path_rank            integer CHECK (path_rank IS NULL OR path_rank >= 1),
            path_feasible        boolean NOT NULL,
            UNIQUE (run_id, path_id, step),
            CHECK (path_feasible OR path_rank IS NULL)
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE transitions")
    op.execute("DROP TYPE transition_action")
