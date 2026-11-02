"""Keep original invoice evidence and award an invoice commission only once."""
from alembic import op

revision = '018_invoice_payment_proof'
down_revision = '017_commission_branch_scope'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE commission_document_files (
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        source_hash VARCHAR(64) NOT NULL,
        filename VARCHAR(255) NOT NULL,
        file_content BYTEA NOT NULL,
        uploaded_by_user_id INTEGER NOT NULL REFERENCES users(id),
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY(franchise_user_id,source_hash))''')
    op.execute('ALTER TABLE commission_entries ADD COLUMN invoice_document_id INTEGER NULL REFERENCES commission_documents(id)')
    op.execute("CREATE UNIQUE INDEX uq_invoice_employee_award ON commission_entries(invoice_document_id,employee_user_id) WHERE commission_type='invoice_commission' AND invoice_document_id IS NOT NULL")


def downgrade():
    pass  # Preserve financial evidence and award history.
