"""M1 : licences, sources, observations (valid time, SRID 4326, qualité dans [0,1]).

Revision ID: 0002
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_QUALITY_DIMS = (
    "source_reliability", "spatial_precision", "temporal_precision", "construct_validity",
    "representativeness", "license_usability", "privacy_usability",
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE licenses (
            license_id           text PRIMARY KEY,
            name                 text NOT NULL,
            url                  text,
            redistribution       boolean NOT NULL,
            commercial_use       boolean NOT NULL,
            attribution_required boolean NOT NULL,
            share_alike          boolean NOT NULL
        )""")
    op.execute("""
        CREATE TABLE sources (
            source_id       uuid PRIMARY KEY,
            slug            text NOT NULL,
            name            text NOT NULL,
            provider        text NOT NULL,
            release         text NOT NULL,
            retrieved_at    timestamptz NOT NULL,
            url             text,
            citation        text NOT NULL,
            license_id      text NOT NULL REFERENCES licenses (license_id),
            method          text NOT NULL,
            temporal_start  date,
            temporal_end    date,
            spatial_extent  geometry(Geometry, 4326),
            privacy_class   privacy_class NOT NULL,
            data_zone       data_zone NOT NULL,
            roles_allowed   text[] NOT NULL,
            roles_forbidden text[] NOT NULL,
            checksum        text NOT NULL,
            manifest_hash   text NOT NULL,
            manifest        jsonb NOT NULL,
            UNIQUE (slug, release),
            CHECK (temporal_start IS NULL OR temporal_end IS NULL OR temporal_start <= temporal_end),
            CHECK (NOT (roles_allowed && roles_forbidden))
        )""")
    quality_checks = " AND ".join(
        f"(quality->>'{d}')::double precision BETWEEN 0 AND 1" for d in _QUALITY_DIMS
    )
    op.execute(f"""
        CREATE TABLE observations (
            observation_id  uuid PRIMARY KEY,
            source_id       uuid NOT NULL REFERENCES sources (source_id),
            variable_id     text NOT NULL,
            ontology_id     uuid,
            support_type    support_type NOT NULL,
            geometry        geometry(Geometry, 4326),
            raster_ref      text,
            admin_code      text,
            displacement_km double precision CHECK (displacement_km IS NULL OR displacement_km > 0),
            valid_from      timestamptz NOT NULL,
            valid_until     timestamptz,
            recorded_at     timestamptz NOT NULL,
            value           jsonb,
            attributes      jsonb NOT NULL,
            quality         jsonb NOT NULL,
            evidence_status evidence_status NOT NULL,
            sensitivity     privacy_class NOT NULL,
            CHECK (valid_until IS NULL OR valid_from <= valid_until),
            CHECK (geometry IS NULL OR ST_IsValid(geometry)),
            CHECK (support_type <> 'UNCERTAIN_POINT' OR displacement_km IS NOT NULL),
            CHECK (support_type <> 'RASTER' OR raster_ref IS NOT NULL),
            CHECK (support_type <> 'NATIONAL' OR admin_code IS NOT NULL),
            CHECK (support_type NOT IN ('POINT', 'UNCERTAIN_POINT', 'POLYGON', 'ADMIN', 'NETWORK')
                   OR geometry IS NOT NULL),
            CHECK ({quality_checks})
        )""")
    op.execute("CREATE INDEX observations_geom_gist ON observations USING gist (geometry)")
    op.execute("CREATE INDEX observations_source_var ON observations (source_id, variable_id)")


def downgrade() -> None:
    op.execute("DROP TABLE observations")
    op.execute("DROP TABLE sources")
    op.execute("DROP TABLE licenses")
