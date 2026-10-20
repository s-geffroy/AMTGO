"""M0 : extension PostGIS, énumérations, manifestes de run, provenance.

Revision ID: 0001
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE TYPE evidence_status AS ENUM ('D', 'P', 'M', 'H', 'U')")
    op.execute("CREATE TYPE privacy_class AS ENUM ('PUBLIC', 'CONTROLLED', 'SENSITIVE', 'PROHIBITED')")
    op.execute("""CREATE TYPE support_type AS ENUM ('POINT', 'UNCERTAIN_POINT', 'POLYGON', 'RASTER',
                  'ADMIN', 'NETWORK', 'HYPEREDGE', 'NATIONAL')""")
    op.execute("""CREATE TYPE data_zone AS ENUM ('OPEN_CORE', 'RESTRICTED_LOCAL', 'SENSITIVE',
                  'DERIVED_EXPORTABLE')""")
    op.execute("""CREATE TYPE recommendation_status AS ENUM ('ROBUST', 'CONDITIONAL', 'EXPLORATORY',
                  'DATA_LIMITED', 'NOT_IDENTIFIABLE')""")
    op.execute("""
        CREATE TABLE run_manifests (
            run_id                  uuid PRIMARY KEY,
            manifest_hash           text NOT NULL UNIQUE CHECK (manifest_hash LIKE 'sha256:%'),
            manifest                jsonb NOT NULL,
            code_commit             text NOT NULL,
            code_version            text NOT NULL,
            data_manifest_hash      text NOT NULL,
            measurement_hash        text,
            causal_library_hash     text,
            normative_manifest_hash text NOT NULL,
            constitutional_regime   text NOT NULL,
            mesh_set                jsonb NOT NULL,
            scenario_set            jsonb NOT NULL,
            solver_manifest         jsonb,
            created_at              timestamptz NOT NULL
        )""")
    op.execute("""
        CREATE TABLE provenance_records (
            record_id      uuid PRIMARY KEY,
            transformation text NOT NULL,
            input_ids      text[] NOT NULL,
            output_ids     text[] NOT NULL CHECK (cardinality(output_ids) > 0),
            code_version   text NOT NULL,
            parameters     jsonb NOT NULL,
            run_id         uuid REFERENCES run_manifests (run_id),
            created_at     timestamptz NOT NULL
        )""")
    op.execute("CREATE INDEX provenance_outputs_gin ON provenance_records USING gin (output_ids)")
    op.execute("CREATE INDEX provenance_inputs_gin ON provenance_records USING gin (input_ids)")


def downgrade() -> None:
    op.execute("DROP TABLE provenance_records")
    op.execute("DROP TABLE run_manifests")
    for t in ("recommendation_status", "data_zone", "support_type", "privacy_class", "evidence_status"):
        op.execute(f"DROP TYPE {t}")
