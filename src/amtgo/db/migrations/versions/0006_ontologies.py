"""M4 : registre des ontologies, concepts et crosswalks (schéma 10 §5-6).

Les ontologies ont des identifiants lisibles et versionnés : les colonnes
``ontology_id`` passent en texte. Aucune table « ethnicity » : il n'existe pas de
classification canonique (prompt §17).

Revision ID: 0006
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE observations ALTER COLUMN ontology_id TYPE text USING ontology_id::text")
    op.execute("ALTER TABLE latent_fields ALTER COLUMN ontology_id TYPE text USING ontology_id::text")
    op.execute("""
        CREATE TABLE ontologies (
            ontology_id     text NOT NULL,
            content_hash    text NOT NULL,
            version         text NOT NULL,
            name            text NOT NULL,
            dimension       text NOT NULL CHECK (dimension IN
                                ('ethnocultural', 'national', 'territorial', 'language', 'religion')),
            kind            text NOT NULL,
            evidence_status evidence_status NOT NULL,
            definition      jsonb NOT NULL,
            PRIMARY KEY (ontology_id, content_hash),
            CHECK (kind <> 'historical' OR evidence_status = 'H')
        )""")
    op.execute("""
        CREATE TABLE ontology_concepts (
            ontology_id     text NOT NULL,
            content_hash    text NOT NULL,
            concept_id      text NOT NULL,
            source_label    text NOT NULL,
            definition      text NOT NULL,
            parent_id       text,
            historical_period daterange,
            self_identified boolean,
            external_label  boolean,
            PRIMARY KEY (ontology_id, content_hash, concept_id),
            FOREIGN KEY (ontology_id, content_hash) REFERENCES ontologies (ontology_id, content_hash)
        )""")
    op.execute("""
        CREATE TABLE ontology_crosswalk (
            crosswalk_id    text NOT NULL,
            content_hash    text NOT NULL,
            source_ontology text NOT NULL,
            target_ontology text NOT NULL,
            source_concept  text NOT NULL,
            target_concept  text NOT NULL,
            probability     double precision NOT NULL CHECK (probability BETWEEN 0 AND 1),
            concentration   double precision NOT NULL CHECK (concentration > 0),
            evidence        jsonb NOT NULL,
            PRIMARY KEY (crosswalk_id, content_hash, source_concept, target_concept)
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE ontology_crosswalk")
    op.execute("DROP TABLE ontology_concepts")
    op.execute("DROP TABLE ontologies")
    op.execute("ALTER TABLE latent_fields ALTER COLUMN ontology_id TYPE uuid USING ontology_id::uuid")
    op.execute("ALTER TABLE observations ALTER COLUMN ontology_id TYPE uuid USING ontology_id::uuid")
