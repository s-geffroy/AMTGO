"""M8 (correctif) : un même candidat peut être généré par plusieurs runs.

L'identifiant de candidat dépend du contenu (maillage, famille, paramètres,
affectation), pas du run : l'unicité porte donc sur (run, candidat, étiquette).

Revision ID: 0010
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE territory_candidates DROP CONSTRAINT territory_candidates_candidate_id_label_key")
    op.execute("ALTER TABLE territory_candidates ADD CONSTRAINT territory_candidates_run_candidate_label_key "
               "UNIQUE (run_id, candidate_id, label)")


def downgrade() -> None:
    op.execute("ALTER TABLE territory_candidates DROP CONSTRAINT territory_candidates_run_candidate_label_key")
    op.execute("ALTER TABLE territory_candidates ADD CONSTRAINT territory_candidates_candidate_id_label_key "
               "UNIQUE (candidate_id, label)")
