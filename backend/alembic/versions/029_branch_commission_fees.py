"""Independent default commission fees for each linked branch."""
from alembic import op

revision='029_branch_commission_fees'
down_revision='028_invoice_layout_name'
branch_labels=None
depends_on=None


def upgrade():
    op.execute('''CREATE TABLE commission_branch_rates (
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        branch_id INTEGER NOT NULL REFERENCES attendance_branches(id),
        rates TEXT NOT NULL DEFAULT '{}',
        updated_by_user_id INTEGER NULL REFERENCES users(id),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY(franchise_user_id,branch_id))''')


def downgrade():
    op.execute('DROP TABLE commission_branch_rates')
