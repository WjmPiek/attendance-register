"""The Mortuary Book's Branch Name owns the MF case, not receipt branding."""
import json

from fastapi import HTTPException
from sqlalchemy import text

from app.services.mortuary import normalise
from app.services.receipt_commissions import branch_key, mf_key


def resolve_record(db, fid, kind, record):
    if kind == 'mortuary':
        return dict(record)
    books = db.execute(text("SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND kind='mortuary' AND mf_key=:mf AND deleted_at IS NULL"),
                       {'fid':fid,'mf':mf_key(record['reference'])}).mappings().all()
    if not books:
        return dict(record)  # May be uploaded before the book; aligned when it arrives.
    matching=[]
    for book in books:
        data=json.loads(book['source_data'])
        if not normalise(data.get('deceased')) or normalise(data.get('deceased')) != normalise(record.get('deceased')):
            continue
        identities={str(value.get('id_number')).strip() for value in (data,record) if value.get('id_number')}
        if len(identities)<=1:
            matching.append((book,data))
    if not matching:
        return dict(record)  # Retain mismatches for review; never reassign them by MF alone.
    direct=[pair for pair in matching if pair[0]['branch_key']==branch_key(record['branch'])]
    choices=direct or matching
    if len(choices)!=1:
        raise HTTPException(409,'More than one Mortuary Book matches this MF number and deceased. The earning branch is ambiguous; correct the documents before saving.')
    book,data=choices[0]
    from app.services.attendance_branches import branches
    from app.services.external_commissions import external_branches
    locations=[b for b in [*branches(db,fid),*external_branches(db,fid)] if branch_key(b['name'])==book['branch_key']]
    if len(locations)!=1:
        raise HTTPException(400,'The Mortuary Book branch is inactive or ambiguous. Correct its branch record before saving evidence.')
    result=dict(record)
    result.setdefault('printed_branch',record['branch'])
    result.update(branch=data['branch'],earning_branch_id=locations[0]['id'],mortuary_branch_document_id=book['id'])
    result['external_branch_id']=locations[0]['id'] if any(b['id']==locations[0]['id'] for b in external_branches(db,fid)) else None
    return result


def align_case_evidence(db, fid, reference, actor=None):
    """Repair unallocated evidence in place; retain IDs, PDFs and original names."""
    from app.services.audit import write_audit_log
    rows=db.execute(text("SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND mf_key=:mf AND kind IN ('invoice','receipt') AND deleted_at IS NULL ORDER BY id"),
                    {'fid':fid,'mf':mf_key(reference)}).mappings().all()
    changed=[]
    for row in rows:
        old=json.loads(row['source_data'])
        updated=resolve_record(db,fid,row['kind'],old)
        key=branch_key(updated['branch'])
        if key==row['branch_key']:
            continue
        used=db.execute(text('SELECT id FROM commission_entries WHERE receipt_document_id=:id OR invoice_document_id=:id OR mortuary_document_id=:id LIMIT 1'),{'id':row['id']}).scalar()
        if used:
            raise HTTPException(409,'This evidence already supports a commission under another branch. Head Office must review it before moving financial records.')
        conflict=db.execute(text("SELECT id FROM commission_documents WHERE franchise_user_id=:fid AND branch_key=:branch AND kind=:kind AND id<>:id AND deleted_at IS NULL AND (document_key=:key OR (:kind='invoice' AND mf_key=:mf))"),
                            {'fid':fid,'branch':key,'kind':row['kind'],'id':row['id'],'key':row['document_key'],'mf':row['mf_key']}).scalar()
        if conflict:
            raise HTTPException(409,'Duplicate evidence exists under the Mortuary Book branch. Review the duplicate documents before finalising.')
        db.execute(text('UPDATE commission_documents SET branch_key=:branch,source_data=:data WHERE id=:id'),{'branch':key,'data':json.dumps(updated),'id':row['id']})
        write_audit_log(db,actor_user_id=actor,franchise_user_id=fid,action='evidence_matched_to_mortuary_branch',entity_type='commission_documents',entity_id=row['id'],
                        old_values={'branch_key':row['branch_key'],'record':old},new_values={'branch_key':key,'record':updated},note='MF and deceased matched; Mortuary Book Branch Name determines commission branch. Rates and staff assignments unchanged.')
        changed.append(row['id'])
    return changed
