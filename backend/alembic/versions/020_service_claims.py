"""Declare outside service branches and prevent duplicate service claims per case."""
from alembic import op

revision = '020_service_claims'
down_revision = '019_staff_weekly_hours'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE external_commission_branches (
        branch_id INTEGER PRIMARY KEY REFERENCES attendance_branches(id),
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        branch_key VARCHAR(255) NOT NULL,
        created_by_user_id INTEGER NOT NULL REFERENCES users(id),
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE(franchise_user_id,branch_key))''')
    op.execute("""CREATE UNIQUE INDEX uq_manual_service_case ON commission_entries
        (franchise_user_id,employee_user_id,commission_type,invoice_document_id)
        WHERE invoice_document_id IS NOT NULL AND status<>'cancelled'
        AND commission_type IN ('grave_service','full_funeral_service','cremation_service','church_service','joinings','overtime','service_other_branch')""")


def downgrade():
    pass  # Preserve financial evidence and branch declarations.
