"""Enforce Version 3 staff ownership boundaries.

The constraints are added NOT VALID so legacy rows can be audited and repaired
without blocking deployment. PostgreSQL still enforces them for every new or
updated row.
"""
from alembic import op


revision = "007_staff_hierarchy_integrity"
down_revision = "006_v3_operational_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_manager_id_franchise
        ON manager_users(id, franchise_user_id)
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_manager_franchise_required'
            ) THEN
                ALTER TABLE manager_users
                ADD CONSTRAINT ck_manager_franchise_required
                CHECK (franchise_user_id IS NOT NULL) NOT VALID;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_employee_franchise_required'
            ) THEN
                ALTER TABLE employee_users
                ADD CONSTRAINT ck_employee_franchise_required
                CHECK (franchise_user_id IS NOT NULL) NOT VALID;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_employee_manager_same_franchise'
            ) THEN
                ALTER TABLE employee_users
                ADD CONSTRAINT fk_employee_manager_same_franchise
                FOREIGN KEY (manager_user_id, franchise_user_id)
                REFERENCES manager_users(id, franchise_user_id)
                NOT VALID;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("""
        ALTER TABLE employee_users
        DROP CONSTRAINT IF EXISTS fk_employee_manager_same_franchise
    """)
    op.execute("""
        ALTER TABLE employee_users
        DROP CONSTRAINT IF EXISTS ck_employee_franchise_required
    """)
    op.execute("""
        ALTER TABLE manager_users
        DROP CONSTRAINT IF EXISTS ck_manager_franchise_required
    """)
    op.execute("DROP INDEX IF EXISTS uq_manager_id_franchise")
