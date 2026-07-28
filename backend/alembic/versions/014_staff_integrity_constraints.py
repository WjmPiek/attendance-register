"""Strengthen staff integrity constraints for new writes.

Existing legacy data may still need repair, so constraints are added NOT VALID
where PostgreSQL allows it. New and updated rows are still enforced.
"""
from alembic import op


revision = "014_staff_integrity_constraints"
down_revision = "013_single_use_office_codes"
branch_labels = None
depends_on = None


def _add_constraint(name: str, sql: str) -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = '{name}'
            ) THEN
                {sql}
            END IF;
        END $$;
    """)


def upgrade():
    _add_constraint(
        "fk_manager_user_account",
        """
        ALTER TABLE manager_users
        ADD CONSTRAINT fk_manager_user_account
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        NOT VALID;
        """,
    )
    _add_constraint(
        "fk_employee_user_account",
        """
        ALTER TABLE employee_users
        ADD CONSTRAINT fk_employee_user_account
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        NOT VALID;
        """,
    )
    _add_constraint(
        "fk_manager_franchise_profile",
        """
        ALTER TABLE manager_users
        ADD CONSTRAINT fk_manager_franchise_profile
        FOREIGN KEY (franchise_user_id)
        REFERENCES franchise_users(id)
        NOT VALID;
        """,
    )
    _add_constraint(
        "fk_employee_franchise_profile",
        """
        ALTER TABLE employee_users
        ADD CONSTRAINT fk_employee_franchise_profile
        FOREIGN KEY (franchise_user_id)
        REFERENCES franchise_users(id)
        NOT VALID;
        """,
    )
    _add_constraint(
        "fk_gps_allocation_user_account",
        """
        ALTER TABLE gps_allocations_per_user
        ADD CONSTRAINT fk_gps_allocation_user_account
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        NOT VALID;
        """,
    )
    _add_constraint(
        "fk_gps_allocation_area",
        """
        ALTER TABLE gps_allocations_per_user
        ADD CONSTRAINT fk_gps_allocation_area
        FOREIGN KEY (area_id)
        REFERENCES areas(id)
        NOT VALID;
        """,
    )


def downgrade():
    for name, table in [
        ("fk_gps_allocation_area", "gps_allocations_per_user"),
        ("fk_gps_allocation_user_account", "gps_allocations_per_user"),
        ("fk_employee_franchise_profile", "employee_users"),
        ("fk_manager_franchise_profile", "manager_users"),
        ("fk_employee_user_account", "employee_users"),
        ("fk_manager_user_account", "manager_users"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
