"""Retain monthly PDF statements and apply the automatic finance schedule."""
from alembic import op

revision = '024_claim_statements'
down_revision = '023_remove_duplicate_branches'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE commission_monthly_reports ADD COLUMN IF NOT EXISTS pdf_content BYTEA')
    # Sent/uncertain reports and their reservations remain immutable.
    op.execute("""UPDATE commission_monthly_reports SET
        period_start=(date_trunc('month',to_date(month_key,'YYYY-MM'))-interval '1 month'+interval '25 days')::date,
        period_end=(date_trunc('month',to_date(month_key,'YYYY-MM'))+interval '24 days')::date,
        send_on=date_trunc('month',to_date(month_key,'YYYY-MM'))+interval '24 days 17 hours',
        recipient_email='wjm@martinsdirect.com, finance@martinsdirect.com'
        WHERE status='scheduled' AND month_key>=to_char(NOW() AT TIME ZONE 'Africa/Johannesburg','YYYY-MM')""")


def downgrade():
    pass  # Preserve delivered financial statements.
