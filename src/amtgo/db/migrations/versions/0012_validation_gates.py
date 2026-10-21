"""M11 : gates de publication (05 §20) et catégorie des solutions (05 §21).

Une ligne par gate et par run. La catégorie de publication d'un run est
reportée sur ses solutions ; une solution ne peut être ROBUST ou CONDITIONAL
que si tous les gates applicables de son run sont passés (la base refuse
l'inverse par déclencheur), et la classe d'accès reste non PUBLIC (0011).

Revision ID: 0012
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE validation_gates (
            run_id     uuid NOT NULL REFERENCES run_manifests (run_id),
            gate       text NOT NULL CHECK (gate IN ('M', 'C', 'O', 'S', 'R')),
            status     text NOT NULL CHECK (status IN ('PASSED', 'FAILED', 'NOT_EVALUABLE', 'NOT_APPLICABLE')),
            detail     jsonb NOT NULL,
            PRIMARY KEY (run_id, gate)
        )""")
    op.execute("""
        CREATE FUNCTION solutions_require_gates() RETURNS trigger AS $$
        BEGIN
            IF NEW.status IN ('ROBUST', 'CONDITIONAL') AND EXISTS (
                SELECT 1 FROM validation_gates g
                WHERE g.run_id = NEW.run_id AND g.status NOT IN ('PASSED', 'NOT_APPLICABLE')
            ) OR NEW.status IN ('ROBUST', 'CONDITIONAL') AND NOT EXISTS (
                SELECT 1 FROM validation_gates g WHERE g.run_id = NEW.run_id
            ) THEN
                RAISE EXCEPTION 'solution % : statut % sans tous les gates passés', NEW.solution_id, NEW.status;
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql""")
    op.execute("""
        CREATE TRIGGER solutions_require_gates BEFORE INSERT OR UPDATE ON solutions
        FOR EACH ROW EXECUTE FUNCTION solutions_require_gates()""")


def downgrade() -> None:
    op.execute("DROP TRIGGER solutions_require_gates ON solutions")
    op.execute("DROP FUNCTION solutions_require_gates()")
    op.execute("DROP TABLE validation_gates")
