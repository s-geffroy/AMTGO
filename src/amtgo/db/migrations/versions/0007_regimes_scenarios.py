"""M6 : régimes constitutionnels typés et scénarios versionnés (schéma 10 §16-17).

``infrastructure_rules`` et ``declared_border`` étendent le schéma 10 §16
(ADR-0018). Les garde-fous de déplacement sont des contraintes de la table : un
scénario qui porterait un déplacement forcé ne peut pas être enregistré.

Revision ID: 0007
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE constitutional_regimes (
            regime_id             text NOT NULL,
            content_hash          text NOT NULL CHECK (content_hash LIKE 'sha256:%'),
            name                  text NOT NULL,
            version               text NOT NULL,
            mobility_rules        jsonb NOT NULL,
            fiscal_transfer_rules jsonb NOT NULL,
            defence_rules         jsonb NOT NULL,
            market_rules          jsonb NOT NULL,
            resource_rules        jsonb NOT NULL,
            infrastructure_rules  jsonb NOT NULL,
            declared_border       jsonb NOT NULL,
            PRIMARY KEY (regime_id, content_hash)
        )""")
    op.execute("""
        CREATE TABLE scenarios (
            scenario_id     text NOT NULL,
            content_hash    text NOT NULL CHECK (content_hash LIKE 'sha256:%'),
            version         text NOT NULL,
            mobility_regime text NOT NULL CHECK (mobility_regime IN ('S1', 'S2A', 'S2C')),
            horizon_years   integer NOT NULL CHECK (horizon_years > 0),
            population      jsonb NOT NULL,
            climate         jsonb NOT NULL,
            urbanization    jsonb NOT NULL,
            economy         jsonb NOT NULL,
            migration       jsonb NOT NULL,
            infrastructure  jsonb NOT NULL,
            security        jsonb NOT NULL,
            PRIMARY KEY (scenario_id, content_hash),
            CHECK ((migration->>'forced_migration')::double precision = 0),
            CHECK ((migration->>'reform_induced_relocation')::double precision = 0)
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE scenarios")
    op.execute("DROP TABLE constitutional_regimes")
