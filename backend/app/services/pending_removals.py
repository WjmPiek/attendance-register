"""Unpaid document estimates; never part of the payable ledger."""
import json
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text

from app.services.attendance_branches import branches, import_staff
from app.services.external_commissions import external_branches, permission_branch
from app.services.receipt_commissions import branch_key, mf_key, enabled_for_branch, effective_branch_rates
from app.services.mortuary import price_removal


def removal_estimate(db, fid, uid, record, role, person, policies, branch_id):
    from app.api.mortuary import effective_policy
    policy = effective_policy(policies, uid)
    policy['rates'].update(effective_branch_rates(db, fid, uid, permission_branch(db, fid, uid, branch_id)))
    return price_removal(record, role, policy, effective_policy(policies, 0).get('extra_holidays', []), staff_hours=person)


def pending_rows(db, fid, user, employee_id=None, from_date=None, to_date=None, status=None, search=None, branch_id=None):
    from app.api.commission import _profile, _participant, _staff_enabled_rows
    from app.api.mortuary import policy_map
    if not fid or status not in (None, 'pending'):
        return []
    _, _, _, _, kind = _profile(db, user)
    if employee_id:
        _participant(db, user, employee_id)
    elif kind not in {'franchise', 'super'}:
        employee_id = user.id
    staff = {p['user_id']:p for p in import_staff(db, fid) if not employee_id or p['user_id']==employee_id}
    if not staff:
        return []
    available = [*branches(db, fid), *external_branches(db, fid)]
    policies = policy_map(db, fid)
    existing = db.execute(text("SELECT employee_user_id,reference,branch_name,commission_type FROM commission_entries WHERE franchise_user_id=:fid AND commission_type IN ('removals','invoice_commission','service_other_branch')"), {'fid':fid}).mappings().all()
    recorded = {(r['employee_user_id'], branch_key(r['branch_name']), mf_key((r['reference'] or '').split(' / Invoice ',1)[0].split(' / Receipt ',1)[0]), r['commission_type']) for r in existing}
    books = db.execute(text("SELECT d.*,s.employee_user_id,s.removal_role FROM commission_documents d JOIN commission_document_staff s ON s.document_id=d.id WHERE d.franchise_user_id=:fid AND d.kind='mortuary' AND d.deleted_at IS NULL ORDER BY d.id"), {'fid':fid}).mappings().all()
    result = []
    seen = set()
    for book in books:
        uid = book['employee_user_id']
        if uid not in staff:
            continue
        record = json.loads(book['source_data'])
        day = date.fromisoformat(record['service_date'])
        if (from_date and day<from_date) or (to_date and day>to_date):
            continue
        matching = [b for b in available if branch_key(b['name'])==book['branch_key']]
        if len(matching)!=1 or (branch_id and matching[0]['id']!=branch_id):
            continue
        branch = matching[0]
        role = book['removal_role'] or 'driver'
        person = staff[uid]
        try:
            permission = permission_branch(db, fid, uid, branch['id'])
            if not enabled_for_branch(db, fid, uid, 'removals', permission):
                continue
            fee = removal_estimate(db, fid, uid, record, role, person, policies, branch['id'])
        except (HTTPException, ValueError, TypeError):
            continue
        categories = [('removals', fee.get('amount'), fee)]
        from app.services.external_commissions import is_external, outside_group
        if is_external(db, fid, branch['id']) and outside_group(db, fid, branch['name']) and enabled_for_branch(db,fid,uid,'service_other_branch',permission):
            from app.services.service_claims import fixed_rate
            try:
                extra = str(fixed_rate(db,fid,uid,'service_other_branch',role,branch['id']))
            except HTTPException:
                extra = None
            categories.append(('service_other_branch', extra, {'fee_label':'Outside branch additional fee'}))
        for category, amount, details in categories:
            key = (uid, book['branch_key'], book['mf_key'], category)
            if key in recorded or key in seen:
                continue
            seen.add(key)
            if search and search.lower() not in f"{record['reference']} {person['full_name']} {category}".lower():
                continue
            reason = 'Waiting for matching invoice and receipts that balance the invoice.'
            if amount is None:
                reason = 'The holder must configure this removal fee. Matching invoice and balanced receipts are also required.'
            result.append({'id':f"book:{book['id']}:{uid}:{category}", 'document_estimate':True,
                'franchise_user_id':fid,'employee_user_id':uid,'employee_name':person['full_name'],
                'employee_number':person.get('employee_number'),'staff_role':person.get('staff_type'),
                'commission_type':category,'service_date':record['service_date'],'reference':record['reference'],
                'quantity':1,'applied_rate':amount or '0','calculated_amount':amount or '0','expected_amount':amount or '0',
                'status':'pending','payment_eligible':False,'payment_block_reason':reason,
                'branch_name':branch['name'],'earning_branch_id':branch['id'],'mortuary_document_id':book['id'],
                'claim_deceased':record.get('deceased'),'commission_role':role,'fee_label':details.get('fee_label'),
                'source_metadata':json.dumps({**record,**details,'role':role}), 'notes':'', 'hours':None,
                'hourly_rate':None,'invoice_value_before_tax':None,'created_by_user_id':book['created_by_user_id']})
    result+=pending_invoices(db,fid,staff,available,policies,recorded,from_date,to_date,search,branch_id)
    return _staff_enabled_rows(db,user,result)


def pending_invoices(db,fid,staff,available,policies,recorded,from_date,to_date,search,branch_id):
    from app.services.receipt_commissions import invoice_commission_rate, resolve_commission_vat, money
    from app.api.receipt_commissions import receipt_settings
    from app.services.mortuary import normalise
    docs=db.execute(text('SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND deleted_at IS NULL ORDER BY id'),{'fid':fid}).mappings().all()
    result=[];seen=set()
    for invoice in [d for d in docs if d['kind']=='invoice']:
        data=json.loads(invoice['source_data']);day=date.fromisoformat(data['service_date'])
        if (from_date and day<from_date) or (to_date and day>to_date):continue
        matched=[b for b in available if branch_key(b['name'])==invoice['branch_key']]
        if len(matched)!=1 or (branch_id and matched[0]['id']!=branch_id):continue
        branch=matched[0]
        case=[d for d in docs if (d['branch_key'],d['mf_key'])==(invoice['branch_key'],invoice['mf_key'])]
        def same_person(doc):
            other=json.loads(doc['source_data'])
            return normalise(other.get('deceased'))==normalise(data.get('deceased')) and bool(normalise(data.get('deceased'))) and not (other.get('id_number') and data.get('id_number') and other['id_number']!=data['id_number'])
        books=[d for d in case if d['kind']=='mortuary' and same_person(d)]
        receipts=[d for d in case if d['kind']=='receipt' and same_person(d)]
        candidates=receipts or books
        people={}
        for document in candidates:
            for person in db.execute(text('SELECT employee_user_id,removal_role FROM commission_document_staff WHERE document_id=:id'),{'id':document['id']}).mappings():
                # Use the same conservative role choice as approval across receipts.
                uid=person['employee_user_id'];role=person['removal_role'] or 'driver'
                people[uid]='assistant' if people.get(uid)=='assistant' or role=='assistant' else 'driver'
        for uid,role in people.items():
            identity=(uid,invoice['branch_key'],invoice['mf_key'],'invoice_commission')
            if uid not in staff or identity in recorded or identity in seen:continue
            if search and search.lower() not in f"{data['reference']} {staff[uid]['full_name']} invoice_commission".lower():continue
            if not enabled_for_branch(db,fid,uid,'invoice_commission',permission_branch(db,fid,uid,branch['id'])):continue
            seen.add(identity)
            rate=invoice_commission_rate(db,fid,uid,role,branch['id'],policies,receipt_settings(db,fid,branch['id']))
            tax={};reason='Waiting for matching Mortuary Book and receipts that balance the full invoice.';amount=None
            try:
                tax=resolve_commission_vat(db,fid,branch['id'],data)
                if rate is not None:amount=str(money(Decimal(tax['commission_base'])*Decimal(str(rate))/100))
                else:reason='Configure the invoice commission percentage. Matching documents and balanced receipts are also required.'
            except HTTPException as exc:reason=exc.detail
            result.append({'id':f"invoice:{invoice['id']}:{uid}",'document_estimate':True,'franchise_user_id':fid,
                'employee_user_id':uid,'employee_name':staff[uid]['full_name'],'employee_number':staff[uid].get('employee_number'),
                'commission_type':'invoice_commission','service_date':data['service_date'],'reference':data['reference'],
                'quantity':1,'applied_rate':str(rate or 0),'calculated_amount':amount or '0','expected_amount':amount or '0',
                'status':'pending','payment_eligible':False,'payment_block_reason':reason,'branch_name':branch['name'],
                'earning_branch_id':branch['id'],'invoice_document_id':invoice['id'],'mortuary_document_id':books[0]['id'] if len(books)==1 else None,
                'claim_deceased':data.get('deceased'),'commission_role':role,'fee_label':'Invoice commission',
                'source_metadata':json.dumps({**data,**tax,'role':role}),'notes':'','hours':None,'hourly_rate':None,
                'invoice_value_before_tax':tax.get('commission_base'),'created_by_user_id':invoice['created_by_user_id']})
    return result
