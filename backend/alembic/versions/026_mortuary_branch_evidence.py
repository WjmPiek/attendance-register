"""Repair the confirmed Benoni MF case using its Mortuary Book branch."""
from alembic import op
from sqlalchemy import text
import json

revision='026_mortuary_branch_evidence'
down_revision='025_commission_carry_forward'
branch_labels=None
depends_on=None


def upgrade():
    from app.services.mf_evidence import align_case_evidence
    bind=op.get_bind()
    books=bind.execute(text("SELECT source_data FROM commission_documents WHERE franchise_user_id=3 AND mf_key='111126' AND kind='mortuary' AND branch_key='benoni' AND deleted_at IS NULL")).scalars().all()
    invoices=bind.execute(text("SELECT source_data FROM commission_documents WHERE franchise_user_id=3 AND mf_key='111126' AND kind='invoice' AND deleted_at IS NULL")).scalars().all()
    if len(books)==1 and any(str(json.loads(value).get('invoice_number'))=='466' for value in invoices):
        align_case_evidence(bind,3,'111126')


def downgrade():
    pass  # Preserve the audited correction and original PDF evidence.
