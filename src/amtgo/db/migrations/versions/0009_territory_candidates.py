"""M8 : candidats territoriaux (schéma 10 §7).

Une ligne par territoire (juridiction) d'un candidat. Ce sont des unités
analytiques : ``active`` reste faux tant qu'aucun optimiseur ni aucune gate ne
les a retenues, et ce registre n'alimente jamais la carte publique.

Revision ID: 0009
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE territory_candidates (
            territory_id      uuid PRIMARY KEY,
            candidate_id      uuid NOT NULL,
            run_id            uuid NOT NULL REFERENCES run_manifests (run_id),
            mesh_id           text NOT NULL,
            level             text NOT NULL,
            label             integer NOT NULL CHECK (label >= 0),
            geometry          geometry(MultiPolygon, 4326) NOT NULL CHECK (ST_IsValid(geometry)),
            generation_method text NOT NULL,
            family            text NOT NULL,
            seed              text NOT NULL,
            active            boolean NOT NULL DEFAULT false,
            UNIQUE (candidate_id, label)
        )""")
    op.execute("CREATE INDEX territory_candidates_geom ON territory_candidates USING gist (geometry)")


def downgrade() -> None:
    op.execute("DROP TABLE territory_candidates")
