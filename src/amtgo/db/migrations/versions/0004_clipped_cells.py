"""M2 (révision) : cellules découpées sur l'emprise.

La règle d'appartenance passe de « centre dans l'emprise » à « intersecte
l'emprise, géométrie découpée » (ADR-0007). Une cellule côtière découpée peut
être multi-surfacique : la colonne passe en MultiPolygon, et ``clipped`` dit
si la cellule est entière.

Revision ID: 0004
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cells DROP CONSTRAINT IF EXISTS cells_geometry_check")
    op.execute("""ALTER TABLE cells ALTER COLUMN geometry TYPE geometry(MultiPolygon, 4326)
                  USING ST_Multi(geometry)""")
    op.execute("ALTER TABLE cells ADD CONSTRAINT cells_geometry_valid CHECK (ST_IsValid(geometry))")
    op.execute("ALTER TABLE cells ADD COLUMN clipped boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE cells DROP COLUMN clipped")
    op.execute("ALTER TABLE cells DROP CONSTRAINT cells_geometry_valid")
    op.execute("""ALTER TABLE cells ALTER COLUMN geometry TYPE geometry(Polygon, 4326)
                  USING ST_GeometryN(geometry, 1)""")
    op.execute("ALTER TABLE cells ADD CONSTRAINT cells_geometry_check CHECK (ST_IsValid(geometry))")
