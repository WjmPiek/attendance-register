"""Stabilise the Version 3 commission workflow and retain its audit history."""
from alembic import op


revision = "009_commission_workflow"
down_revision = "008_optional_staff_email"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS commission_entry_audit (
            id SERIAL PRIMARY KEY,
            entry_id INTEGER NOT NULL REFERENCES commission_entries(id) ON DELETE CASCADE,
            action VARCHAR(40) NOT NULL,
            actor_user_id INTEGER NOT NULL REFERENCES users(id),
            old_values TEXT NULL,
            new_values TEXT NULL,
            note TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("ALTER TABLE commission_entries ADD COLUMN IF NOT EXISTS is_cancelled BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE commission_entries ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP NULL")
    op.execute("ALTER TABLE commission_entries ADD COLUMN IF NOT EXISTS cancelled_by_user_id INTEGER NULL REFERENCES users(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_audit_entry_created ON commission_entry_audit(entry_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_entries_reference_lookup ON commission_entries(franchise_user_id, employee_user_id, service_date, commission_type)")


def downgrade():
    # Intentionally non-destructive: financial workflow history must be retained.
    pass
