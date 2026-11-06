"""Retain document corrections and permit replacement of archived evidence."""
from alembic import op
from sqlalchemy import inspect

revision = '022_commission_document_register'
down_revision = '021_commission_delivery'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE employee_commission_branch_overrides (
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        employee_user_id INTEGER NOT NULL REFERENCES users(id),
        branch_id INTEGER NOT NULL REFERENCES attendance_branches(id),
        rates TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(franchise_user_id,employee_user_id,branch_id))''')
    op.execute('''INSERT INTO employee_commission_branch_overrides(franchise_user_id,employee_user_id,branch_id)
        SELECT DISTINCT franchise_user_id,employee_user_id,branch_id FROM employee_commission_branch_options''')
    op.execute('ALTER TABLE commission_documents ADD COLUMN deleted_at TIMESTAMP NULL')
    op.execute('ALTER TABLE commission_documents ADD COLUMN deleted_by_user_id INTEGER NULL REFERENCES users(id)')
    op.execute('ALTER TABLE commission_documents ADD COLUMN deletion_reason TEXT NULL')
    expected = {'franchise_user_id', 'kind', 'branch_key', 'document_key'}
    for constraint in inspect(op.get_bind()).get_unique_constraints('commission_documents'):
        if set(constraint['column_names']) == expected:
            op.drop_constraint(constraint['name'], 'commission_documents', type_='unique')
    op.execute('CREATE UNIQUE INDEX uq_active_commission_document ON commission_documents(franchise_user_id,kind,branch_key,document_key) WHERE deleted_at IS NULL')
    op.execute('CREATE INDEX ix_commission_document_upload_month ON commission_documents(franchise_user_id,created_at,id)')


def downgrade():
    pass  # Keep corrections, original evidence and financial history.
