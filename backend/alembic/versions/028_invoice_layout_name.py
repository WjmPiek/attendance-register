"""Restore the final surname glyph from Rivonia's original invoice PDF."""
import json
from decimal import Decimal
from hashlib import sha256
from alembic import op
from sqlalchemy import text

revision='028_invoice_layout_name'
down_revision='027_wrapped_receipt_name'
branch_labels=None
depends_on=None


def repair_invoice_name(db,fid,reference,invoice_number):
    from app.services.audit import write_audit_log
    from app.services.invoice_proof import parse_invoice_pdf
    from app.services.mortuary import normalise
    from app.services.receipt_commissions import mf_key
    docs=db.execute(text('SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND mf_key=:mf AND deleted_at IS NULL'),{'fid':fid,'mf':mf_key(reference)}).mappings().all()
    books=[row for row in docs if row['kind']=='mortuary']
    invoices=[row for row in docs if row['kind']=='invoice']
    receipts=[row for row in docs if row['kind']=='receipt']
    if len(books)!=1 or len(invoices)!=1 or not receipts:return 0
    row=invoices[0];old=json.loads(row['source_data']);book=json.loads(books[0]['source_data'])
    expected=normalise(book.get('deceased'))
    if str(old.get('invoice_number'))!=str(invoice_number) or normalise(old.get('deceased'))==expected:return 0
    if any(doc['branch_key']!=row['branch_key'] for doc in docs):return 0
    if not expected or any(normalise(json.loads(doc['source_data']).get('deceased'))!=expected for doc in receipts):return 0
    content=db.execute(text('SELECT file_content FROM commission_document_files WHERE franchise_user_id=:fid AND source_hash=:hash'),{'fid':fid,'hash':row['source_hash']}).scalar()
    if not content or sha256(bytes(content)).hexdigest()!=row['source_hash']:return 0
    records,errors=parse_invoice_pdf(bytes(content))
    candidates=[record for record in records if mf_key(record['reference'])==row['mf_key'] and str(record['invoice_number'])==str(invoice_number)]
    if errors or len(candidates)!=1:return 0
    parsed=candidates[0]
    if normalise(parsed['deceased'])!=expected or not expected.startswith(normalise(old.get('deceased'))):return 0
    if any(str(parsed.get(key) or '')!=str(old.get(key) or '') for key in ('service_date','id_number')):return 0
    if Decimal(parsed['invoice_total'])!=Decimal(old['invoice_total']):return 0
    updated={**old,'deceased':parsed['deceased']}
    db.execute(text('UPDATE commission_documents SET source_data=:data WHERE id=:id'),{'data':json.dumps(updated),'id':row['id']})
    write_audit_log(db,actor_user_id=None,franchise_user_id=fid,action='invoice_layout_name_reparsed',entity_type='commission_documents',entity_id=row['id'],old_values=old,new_values=updated,
                   note='Recovered the complete name from the hash-verified original invoice PDF. Book and every receipt agree; financial values, branch and source PDF unchanged.')
    return 1


def upgrade():
    repair_invoice_name(op.get_bind(),3,'111105','536')


def downgrade():
    pass
