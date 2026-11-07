"""Record blocked claims carried into the next finance cycle."""
from alembic import op

revision = '025_commission_carry_forward'
down_revision = '024_claim_statements'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE commission_carry_forwards (
        entry_id INTEGER NOT NULL REFERENCES commission_entries(id),
        source_report_id INTEGER NOT NULL REFERENCES commission_monthly_reports(id),
        source_month VARCHAR(7) NOT NULL, target_month VARCHAR(7) NOT NULL,
        target_start DATE NOT NULL, target_end DATE NOT NULL,
        estimated_amount NUMERIC(14,2), reason TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY(entry_id,source_report_id))''')
    op.execute('CREATE INDEX ix_commission_carry_latest ON commission_carry_forwards(entry_id,target_month DESC)')


def downgrade():
    pass  # Retain financial carry-forward and notification history.
