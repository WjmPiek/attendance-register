"""Store each manager and employee's daily working hours in the staff register."""
from alembic import op

revision = '019_staff_weekly_hours'
down_revision = '018_invoice_payment_proof'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE manager_users ADD COLUMN work_week TEXT NULL')
    op.execute('ALTER TABLE employee_users ADD COLUMN work_week TEXT NULL')


def downgrade():
    pass  # Retain saved staff schedules.
