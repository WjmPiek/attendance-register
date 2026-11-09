"""Reparse the confirmed Northcliff receipt whose surname wrapped onto a new line."""
import json
from decimal import Decimal
from hashlib import sha256

from alembic import op
from sqlalchemy import text

revision='027_wrapped_receipt_name'
down_revision='026_mortuary_branch_evidence'
branch_labels=None
depends_on=None


def repair_receipt_name(db, fid, reference, receipt_number):
    from app.services.audit import write_audit_log
    from app.services.mortuary import normalise
    from app.services.receipt_commissions import mf_key, parse_receipt_pdf
    params={'fid':fid,'mf':mf_key(reference)}
    docs=db.execute(text("SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND mf_key=:mf AND deleted_at IS NULL"),params).mappings().all()
    books=[row for row in docs if row['kind']=='mortuary']
    invoices=[row for row in docs if row['kind']=='invoice']
    if len(books)!=1 or len(invoices)!=1:return 0
    if books[0]['branch_key']!=invoices[0]['branch_key']:return 0
    book,invoice=json.loads(books[0]['source_data']),json.loads(invoices[0]['source_data'])
    expected=normalise(book.get('deceased'))
    if not expected or normalise(invoice.get('deceased'))!=expected:return 0
    repaired=0
    for row in docs:
        if row['kind']!='receipt' or row['branch_key']!=books[0]['branch_key']:continue
        old=json.loads(row['source_data'])
        previous=normalise(old.get('deceased'))
        if str(old.get('receipt_number'))!=str(receipt_number) or not previous or not expected.startswith(previous+' '):continue
        content=db.execute(text('SELECT file_content FROM commission_document_files WHERE franchise_user_id=:fid AND source_hash=:hash'),{'fid':fid,'hash':row['source_hash']}).scalar()
        if not content or sha256(bytes(content)).hexdigest()!=row['source_hash']:continue
        records,errors=parse_receipt_pdf(bytes(content))
        candidates=[record for record in records if mf_key(record['reference'])==row['mf_key'] and str(record['receipt_number'])==str(receipt_number)]
        if errors or len(candidates)!=1:continue
        parsed=candidates[0]
        if normalise(parsed['deceased'])!=expected:continue
        if any(str(parsed.get(key) or '')!=str(old.get(key) or '') for key in ('invoice_number','id_number','service_date')):continue
        if str(parsed.get('id_number') or '')!=str(book.get('id_number') or ''):continue
        if Decimal(parsed['gross_received'])!=Decimal(old['gross_received']):continue
        updated={**old,'deceased':parsed['deceased']}
        db.execute(text('UPDATE commission_documents SET source_data=:data WHERE id=:id'),{'data':json.dumps(updated),'id':row['id']})
        write_audit_log(db,actor_user_id=None,franchise_user_id=fid,action='receipt_wrapped_name_reparsed',entity_type='commission_documents',entity_id=row['id'],old_values=old,new_values=updated,
                       note='Reparsed the original hash-verified receipt PDF; full name matches Mortuary Book and invoice. Financial values, branch and original PDF unchanged.')
        repaired+=1
    return repaired


def upgrade():
    repair_receipt_name(op.get_bind(),3,'111137','1502')


def downgrade():
    pass  # Preserve the audited extraction correction and original evidence.
