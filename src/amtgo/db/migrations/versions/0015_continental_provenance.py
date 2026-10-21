"""M14 : provenance des compositions continentales.

Un run continental n'a pas de ligne dans run_manifests (ce n'est pas un run
régional) : sa provenance se rattache à sa composition (``continental_run_id``),
jamais aux deux à la fois.

Revision ID: 0015
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE provenance_records
            ADD COLUMN continental_run_id uuid REFERENCES continental_compositions (run_id),
            ADD CONSTRAINT provenance_single_run CHECK (run_id IS NULL OR continental_run_id IS NULL)""")


def downgrade() -> None:
    op.execute("ALTER TABLE provenance_records DROP COLUMN continental_run_id")
