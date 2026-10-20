"""M10 : archive de Pareto (schéma 10 §18).

Une ligne par solution de l'archive, avec son rang. ``status`` reste
NOT_IDENTIFIABLE tant que les gates de publication (M11) ne sont pas passées :
la base ne peut pas contenir une solution « recommandée » sans elles.

Revision ID: 0011
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE solutions (
            solution_id    uuid PRIMARY KEY,
            run_id         uuid NOT NULL REFERENCES run_manifests (run_id),
            regime_id      text NOT NULL,
            variant_key    text NOT NULL,
            family         text NOT NULL,
            status         recommendation_status NOT NULL,
            feasible       boolean NOT NULL,
            pareto_rank    integer CHECK (pareto_rank IS NULL OR pareto_rank >= 1),
            metrics        jsonb NOT NULL,
            stability      jsonb NOT NULL,
            causal_support jsonb NOT NULL,
            privacy_status privacy_class NOT NULL CHECK (privacy_status <> 'PUBLIC'),
            UNIQUE (run_id, variant_key),
            CHECK (feasible OR pareto_rank IS NULL)
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE solutions")
