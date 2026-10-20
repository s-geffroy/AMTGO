"""M2 : définitions de maillage et cellules analytiques.

Clé des cellules : (mesh_id, definition_hash, cell_id). Une même cellule H3
peut appartenir à plusieurs maillages d'emprises différentes, et un mesh_id peut
être redéfini dans une version ultérieure. Le non-chevauchement au même niveau
est vérifié par le code (geo.mesh.assert_valid_mesh) avant insertion.

Revision ID: 0003
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE mesh_definitions (
            mesh_id         text NOT NULL,
            definition_hash text NOT NULL,
            family          text NOT NULL CHECK (family IN ('h3', 'grid_laea')),
            resolution      integer NOT NULL CHECK (resolution BETWEEN 0 AND 15),
            definition      jsonb NOT NULL,
            cells_hash      text NOT NULL,
            cell_count      integer NOT NULL CHECK (cell_count > 0),
            created_at      timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (mesh_id, definition_hash)
        )""")
    op.execute("""
        CREATE TABLE cells (
            mesh_id         text NOT NULL,
            definition_hash text NOT NULL,
            cell_id         text NOT NULL,
            resolution      integer NOT NULL,
            geometry        geometry(Polygon, 4326) NOT NULL CHECK (ST_IsValid(geometry)),
            parent_cell_id  text,
            area_km2        double precision NOT NULL CHECK (area_km2 > 0),
            PRIMARY KEY (mesh_id, definition_hash, cell_id),
            FOREIGN KEY (mesh_id, definition_hash)
                REFERENCES mesh_definitions (mesh_id, definition_hash)
        )""")
    op.execute("CREATE INDEX cells_geom_gist ON cells USING gist (geometry)")


def downgrade() -> None:
    op.execute("DROP TABLE cells")
    op.execute("DROP TABLE mesh_definitions")
