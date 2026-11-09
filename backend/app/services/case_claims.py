"""MF-only claims wait for document finalisation before becoming payables."""
import json
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import text
from app.core.timezone import now_sa_naive
from app.services.attendance_branches import import_staff
from app.services.external_commissions import permission_branch
from app.services.mortuary import driver_names, match_employee, normalise
from app.services.receipt_commissions import COMMISSION_LABELS, branch_key, enabled_for_branch, mf_key
from app.services.service_claims import CLAIM_TYPES, MANUAL_TYPES, calculate_claim, fixed_rate


def case_branch(db,fid,branch_id,reference):
    selected=db.execute(text('SELECT name FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid AND is_active=TRUE'),{'id':branch_id,'fid':fid}).scalar()
    if not selected:raise HTTPException(403,'Selected branch is outside your active holder group.')
    books=db.execute(text("SELECT branch_key FROM commission_documents WHERE franchise_user_id=:fid AND mf_key=:mf AND kind='mortuary' AND deleted_at IS NULL"),{'fid':fid,'mf':mf_key(reference)}).scalars().all()
    if not books or branch_key(selected) in books:return branch_id
    if len(set(books))!=1:raise HTTPException(409,'Multiple Mortuary Book branches use this MF number. Select the branch printed on your book.')
    choices=db.execute(text('SELECT id,name FROM attendance_branches WHERE franchise_user_id=:fid AND is_active=TRUE'),{'fid':fid}).mappings().all()
    matched=[row['id'] for row in choices if branch_key(row['name'])==books[0]]
    if len(matched)!=1:raise HTTPException(400,'The Mortuary Book branch is inactive or ambiguous.')
    return matched[0]


def removal_applicability(db,fid,uid,branch_id,reference):
    """None means evidence is not yet sufficient; False means another crew did it."""
    try:branch_id=case_branch(db,fid,branch_id,reference)
    except HTTPException:return None
    name=db.execute(text('SELECT name FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid'),{'id':branch_id,'fid':fid}).scalar()
    books=db.execute(text("SELECT source_data FROM commission_documents WHERE franchise_user_id=:fid AND branch_key=:branch AND mf_key=:mf AND kind='mortuary' AND deleted_at IS NULL"),{'fid':fid,'branch':branch_key(name),'mf':mf_key(reference)}).scalars().all()
    if len(books)!=1:return None
    names=driver_names(json.loads(books[0]).get('driver_in') or '')
    if not 1<=len(names)<=2:return None
    staff=import_staff(db,fid)
    matches=[match_employee(name,staff) for name in names]
    if matches.count(uid)==1:return True
    if None in matches or len(set(matches))!=len(matches):return None
    return False


def cancel_unrelated_removal(db,row,actor):
    if row['commission_type']!='removals' or row['status']!='pending' or not json.loads(row.get('source_metadata') or '{}').get('mf_case_claim'):return False
    if removal_applicability(db,row['franchise_user_id'],row['employee_user_id'],row['earning_branch_id'],row['reference']) is not False:return False
    from app.api.commission import _audit
    note='Not applicable: this staff member is not listed under Driver In on the imported Mortuary Book.'
    db.execute(text("UPDATE commission_entries SET status='cancelled',is_cancelled=TRUE,review_notes=:note,reviewed_at=NOW(),reviewed_by_user_id=:actor WHERE id=:id AND status='pending'"),{'id':row['id'],'actor':actor,'note':note})
    _audit(db,row['id'],'removal_not_in_driver_in',actor,old=dict(row),note=note)
    return True


def quote_case_item(db, participant, branch_id, reference, category, exclude_id=None):
    from app.api.commission import EntryIn
    fid,uid=participant['franchise_user_id'],participant['user_id']
    branch_id=case_branch(db,fid,branch_id,reference)
    if category=='removals' and removal_applicability(db,fid,uid,branch_id,reference) is False:
        raise HTTPException(403,'Removal commission applies only to staff listed under Driver In on this Mortuary Book.')
    branch=db.execute(text('SELECT name FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid AND is_active=TRUE'),{'id':branch_id,'fid':fid}).scalar()
    if not branch or not enabled_for_branch(db,fid,uid,category,permission_branch(db,fid,uid,branch_id)):
        raise HTTPException(403,'This commission is not enabled for this employee at the selected branch.')
    docs=db.execute(text('SELECT kind,source_data FROM commission_documents WHERE franchise_user_id=:fid AND branch_key=:branch AND mf_key=:mf AND deleted_at IS NULL'),{'fid':fid,'branch':branch_key(branch),'mf':mf_key(reference)}).mappings().all()
    books=[json.loads(row['source_data']) for row in docs if row['kind']=='mortuary']
    invoices=[json.loads(row['source_data']) for row in docs if row['kind']=='invoice']
    book=books[0] if len(books)==1 else {}
    invoice=invoices[0] if len(invoices)==1 else {}
    role='driver'
    matches=[match_employee(name,import_staff(db,fid)) for name in book.get('names',[])]
    if uid in matches and matches.count(uid)==1:
        name=book['names'][matches.index(uid)]
        role='driver' if len(matches)==1 or normalise(name)==normalise(book.get('driver')) else 'assistant'
    payload=EntryIn(employee_user_id=uid,earning_branch_id=branch_id,reference=book.get('reference') or reference,
        commission_type=category,claim_deceased=book.get('deceased') or invoice.get('deceased'),commission_role=role,
        service_date=(book.get('date_in') if category=='removals' else invoice.get('service_date')) or now_sa_naive().date())
    notice='Waiting for the matching Mortuary Book, invoice and fully paid receipts to be checked.'
    if payload.claim_deceased:
        try:
            return payload,calculate_claim(db,None,payload,participant,exclude_id=exclude_id)
        except HTTPException as exc:
            if exc.status_code!=400:raise
            notice=exc.detail
    quote={'branch_id':branch_id,'branch_name':branch,'documents_valid':False,'notice':notice,'proof':{},
        'additional_fee':None,'rate':'0','amount':'0','estimate_available':False,
        'calculation_type':'percentage' if category=='invoice_commission' else 'fixed'}
    if category in MANUAL_TYPES:
        try:
            fee=fixed_rate(db,fid,uid,category,role,branch_id)
            quote.update(rate=str(fee),amount=str(fee),estimate_available=True)
        except HTTPException as exc:
            quote['notice']=exc.detail
    return payload,quote


def allocate_case(db,user,participant,branch_id,reference):
    from app.api.commission import _save_claim_entry
    fid,uid=participant['franchise_user_id'],participant['user_id']
    reference=reference.strip()
    if not mf_key(reference):raise HTTPException(400,'Enter a valid MF File Number.')
    branch_id=case_branch(db,fid,branch_id,reference)
    branch=db.execute(text('SELECT name FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid AND is_active=TRUE'),{'id':branch_id,'fid':fid}).scalar()
    if not branch:raise HTTPException(403,'Selected branch is outside your active holder group.')
    categories=[category for category in COMMISSION_LABELS if category in CLAIM_TYPES and enabled_for_branch(db,fid,uid,category,permission_branch(db,fid,uid,branch_id))]
    if removal_applicability(db,fid,uid,branch_id,reference) is False:
        categories=[category for category in categories if category!='removals']
        if not categories:raise HTTPException(400,'No enabled commissions apply to you for this MF file. Removal fees apply only to the staff listed under Driver In.')
    if not categories:raise HTTPException(403,'No commission items are enabled for you at this branch.')
    existing={}
    for row in db.execute(text("SELECT * FROM commission_entries WHERE franchise_user_id=:fid AND employee_user_id=:uid AND COALESCE(is_cancelled,FALSE)=FALSE AND status<>'cancelled' ORDER BY id"),{'fid':fid,'uid':uid}).mappings():
        if mf_key(row['reference'].split(' / Invoice ',1)[0].split(' / Receipt ',1)[0])!=mf_key(reference):continue
        same=row['earning_branch_id']==branch_id
        if not same and row['status']=='pending' and json.loads(row['source_metadata'] or '{}').get('mf_case_claim'):
            try:same=case_branch(db,fid,row['earning_branch_id'],reference)==branch_id
            except HTTPException:pass
        if same:
            if cancel_unrelated_removal(db,row,user.id):continue
            existing[row['commission_type']]=dict(row)
    items=[];total=Decimal(0);created=0
    for category in categories:
        if category in existing:
            old=existing[category]
            amount=str(old['calculated_amount']);available=True;notice=None
            if old['status']=='pending':
                try:
                    _,quote=quote_case_item(db,participant,branch_id,reference,category,exclude_id=old['id'])
                    amount=quote['amount'];available=quote['estimate_available'];notice=quote['notice']
                except HTTPException as exc:amount='0';available=False;notice=exc.detail
            items.append({'category':category,'state':'existing','status':old['status'],'entry_id':old['id'],'amount':amount,'estimate_available':available,'notice':notice})
            continue
        payload,quote=quote_case_item(db,participant,branch_id,reference,category)
        row=_save_claim_entry(db,user,participant,payload,quote,pending_case=True)
        created+=1;total+=Decimal(quote['amount'])
        items.append({'category':category,'state':'pending','status':'pending','entry_id':row['id'],'amount':quote['amount'],
            'estimate_available':quote['estimate_available'],'notice':quote['notice'] or 'Documents checked; waiting for finalisation.'})
    waiting=sum((Decimal(item['amount']) for item in items if item['status']=='pending'),Decimal(0))
    approved=sum((Decimal(item['amount']) for item in items if item['status']=='approved'),Decimal(0))
    return {'reference':reference,'branch_id':branch_id,'branch_name':branch,'created':created,'total':str((waiting+approved).quantize(Decimal('0.01'))),
        'waiting_total':str(waiting.quantize(Decimal('0.01'))),'approved_total':str(approved.quantize(Decimal('0.01'))),'new_total':str(total.quantize(Decimal('0.01'))),
        'documents_valid':False,'status':'pending' if created else 'existing','items':items,
        'notice':'Claims are saved under Waiting to be finalised. Only finalised amounts move to Approved.' if created else 'These commissions are already recorded. Their existing statuses are unchanged; no duplicates were added.'}
