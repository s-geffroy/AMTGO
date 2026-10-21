"""M14 : compositions continentales (07 §13, 11 phase 10).

Un run continental compose des runs régionaux Map-R déjà enregistrés : la table
garde le manifeste gelé et le produit (archive, interfaces, régimes de conclusion),
et la table de liaison rattache chaque région à son run régional. Aucune géométrie
n'est stockée : une composition n'en produit pas.

Revision ID: 0014
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE continental_compositions (
            run_id               uuid PRIMARY KEY,
            manifest_hash        text NOT NULL,
            manifest             jsonb NOT NULL,
            code_commit          text NOT NULL,
            regime               text NOT NULL,
            conclusion           text NOT NULL,
            publication_category text NOT NULL,
            front_size           integer NOT NULL CHECK (front_size >= 1),
            product              jsonb NOT NULL,
            created_at           timestamptz NOT NULL
        )""")
    op.execute("""
        CREATE TABLE continental_regions (
            run_id          uuid NOT NULL REFERENCES continental_compositions (run_id),
            region_id       text NOT NULL,
            regional_run_id uuid NOT NULL REFERENCES run_manifests (run_id),
            PRIMARY KEY (run_id, region_id)
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE continental_regions")
    op.execute("DROP TABLE continental_compositions")
