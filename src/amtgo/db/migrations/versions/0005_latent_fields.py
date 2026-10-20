"""M3 : champs latents (schéma 10 §4) et gel de mesure.

Les tirages restent dans les artefacts du run (``fields/<mesh>/samples.npy``) ;
la base porte les résumés par cellule et les identifiants de lignée.

Revision ID: 0005
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE latent_fields (
            field_id          uuid PRIMARY KEY,
            run_id            uuid NOT NULL REFERENCES run_manifests (run_id),
            mesh_id           text NOT NULL,
            definition_hash   text NOT NULL,
            variable_id       text NOT NULL,
            time_period       daterange NOT NULL,
            ontology_id       uuid,
            measurement_hash  text NOT NULL,
            model_version     text NOT NULL,
            evidence_status   evidence_status NOT NULL CHECK (evidence_status = 'M'),
            privacy_class     privacy_class NOT NULL,
            computability     text NOT NULL CHECK (computability IN ('A', 'B', 'C', 'D')),
            summary           jsonb NOT NULL,
            samples_hash      text NOT NULL,
            FOREIGN KEY (mesh_id, definition_hash) REFERENCES mesh_definitions (mesh_id, definition_hash)
        )""")
    op.execute("""
        CREATE TABLE latent_field_cells (
            field_id          uuid NOT NULL REFERENCES latent_fields (field_id),
            cell_id           text NOT NULL,
            mean              double precision NOT NULL,
            sd                double precision NOT NULL CHECK (sd >= 0),
            lower_bound       double precision NOT NULL,
            upper_bound       double precision NOT NULL CHECK (lower_bound <= upper_bound),
            information_ratio double precision NOT NULL CHECK (information_ratio BETWEEN 0 AND 1),
            negative_fraction double precision NOT NULL CHECK (negative_fraction BETWEEN 0 AND 1),
            computability     text NOT NULL CHECK (computability IN ('A', 'B', 'C', 'D')),
            PRIMARY KEY (field_id, cell_id)
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE latent_field_cells")
    op.execute("DROP TABLE latent_fields")
