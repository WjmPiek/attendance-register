"""Allocate an authenticated staff member's enabled commissions from MF evidence."""
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text

from app.services.attendance_branches import import_staff
from app.services.external_commissions import permission_branch
from app.services.mortuary import match_employee, normalise
from app.services.receipt_commissions import COMMISSION_LABELS, enabled_for_branch, mf_key, require_payment_proof
from app.services.service_claims import CLAIM_TYPES, calculate_claim


def allocate_case(db, user, participant, branch_id, reference):
    from app.api.commission import EntryIn, _save_claim_entry
    fid, uid = participant['franchise_user_id'], participant['user_id']
    reference = reference.strip()
    if not mf_key(reference):
        raise HTTPException(400, 'Enter a valid MF File Number.')
    branch = db.execute(text('SELECT name FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid AND is_active=TRUE'),
                        {'id':branch_id,'fid':fid}).scalar()
    if not branch:
        raise HTTPException(403, 'Selected branch is outside your active holder group.')
    scope = permission_branch(db, fid, uid, branch_id)
    categories = [category for category in COMMISSION_LABELS if category in CLAIM_TYPES and enabled_for_branch(db,fid,uid,category,scope)]
    if not categories:
        raise HTTPException(403, 'No commission items are enabled for you at this branch. Ask the franchise holder to check your branch commission permissions.')
    response = {'reference':reference, 'branch_id':branch_id, 'branch_name':branch, 'created':0,
                'total':'0.00', 'documents_valid':False, 'items':[], 'notice':None}
    try:
        proof = require_payment_proof(db, fid, branch_id, reference)
    except HTTPException as exc:
        if exc.status_code not in (400,409):
            raise
        return {**response, 'notice':exc.detail}
    books = db.execute(text('SELECT source_data FROM commission_documents WHERE id=:id'), {'id':proof['mortuary_document_id']}).scalar_one()
    invoice = db.execute(text('SELECT source_data FROM commission_documents WHERE id=:id'), {'id':proof['invoice_document_id']}).scalar_one()
    book, invoice = json.loads(books), json.loads(invoice)
    people = import_staff(db, fid)
    matches = [match_employee(name,people) for name in book.get('names',[])]
    role = 'driver'
    if uid in matches and matches.count(uid)==1:
        printed_name = book['names'][matches.index(uid)]
        role = 'driver' if len(matches)==1 or normalise(printed_name)==normalise(book.get('driver')) else 'assistant'
    existing = {row['commission_type']:dict(row) for row in db.execute(text('''SELECT * FROM commission_entries
        WHERE franchise_user_id=:fid AND employee_user_id=:uid AND earning_branch_id=:bid
        AND COALESCE(is_cancelled,FALSE)=FALSE AND status<>'cancelled' '''),
        {'fid':fid,'uid':uid,'bid':branch_id}).mappings()
        if mf_key(row['reference'].split(' / Invoice ',1)[0].split(' / Receipt ',1)[0])==mf_key(reference)}
    total = Decimal(0)
    for category in categories:
        if category in existing:
            old = existing[category]
            response['items'].append({'category':category,'state':'existing','status':old['status'],
                                      'entry_id':old['id'],'amount':str(old['calculated_amount']),
                                      'notice':'Already recorded for this MF File; no duplicate added.'})
            continue
        try:
            payload = EntryIn(employee_user_id=uid, earning_branch_id=branch_id, reference=book['reference'],
                              commission_type=category, claim_deceased=proof['deceased'], commission_role=role,
                              service_date=book['date_in'] if category=='removals' else invoice['service_date'])
            quote = calculate_claim(db, user, payload, participant)
        except HTTPException as exc:
            if exc.status_code not in (400,409):
                raise
            response['items'].append({'category':category,'state':'blocked','notice':exc.detail})
            continue
        if not quote['documents_valid']:
            response['items'].append({'category':category,'state':'blocked','notice':quote['notice']})
            continue
        saved = _save_claim_entry(db, user, participant, payload, quote)
        response['created'] += 1
        total += Decimal(quote['amount'])
        response['items'].append({'category':category,'state':'approved','entry_id':saved['id'],'amount':quote['amount']})
        if quote['additional_fee']:
            fee = quote['additional_fee']
            total += Decimal(fee['amount'])
            response['created'] += 1
            response['items'].append({'category':'service_other_branch','state':'approved','amount':fee['amount']})
    return {**response, 'documents_valid':True, 'total':str(total.quantize(Decimal('0.01'))), 'deceased':proof['deceased']}
