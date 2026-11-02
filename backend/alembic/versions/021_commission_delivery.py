"""Automatic commission reconciliation and configurable monthly finance summaries."""
from alembic import op

revision = '021_commission_delivery'
down_revision = '020_service_claims'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE commission_delivery_settings (
        franchise_user_id INTEGER PRIMARY KEY REFERENCES franchise_users(id),
        recipient_email VARCHAR(255), updated_by_user_id INTEGER REFERENCES users(id),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW())''')
    op.execute('''CREATE TABLE commission_monthly_reports (
        id SERIAL PRIMARY KEY, franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        month_key VARCHAR(7) NOT NULL, period_start DATE NOT NULL, period_end DATE NOT NULL,
        send_on TIMESTAMP NOT NULL, recipient_email VARCHAR(255), subject VARCHAR(255), message TEXT,
        status VARCHAR(30) NOT NULL DEFAULT 'scheduled', sent_at TIMESTAMP, error_message TEXT,
        next_attempt_at TIMESTAMP, created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE(franchise_user_id,month_key))''')
    op.execute('''CREATE TABLE commission_monthly_report_items (
        entry_id INTEGER PRIMARY KEY REFERENCES commission_entries(id),
        report_id INTEGER NOT NULL REFERENCES commission_monthly_reports(id))''')


def downgrade():
    pass  # Retain delivery records and financial reporting history.
