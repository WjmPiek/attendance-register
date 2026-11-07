"""Calculate staff-entered service claims from configured rates and imported proof."""
from decimal import Decimal
import json

from fastapi import HTTPException
from sqlalchemy import text

from app.services.mortuary import normalise
from app.services.receipt_commissions import money, mf_key, require_manual_eligibility, require_payment_proof, enabled_for_branch
from app.services.external_commissions import permission_branch, is_external, outside_group

MANUAL_TYPES = {'grave_service', 'full_funeral_service', 'cremation_service', 'church_service', 'joinings', 'overtime'}
CLAIM_TYPES = MANUAL_TYPES | {'removals', 'invoice_commission'}


def fixed_rate(db, fid, uid, category, role, branch_id=None):
    from app.api.mortuary import policy_map, effective_policy
    key = f'{role}_{"other_branch" if category == "service_other_branch" else category}'
    rate = effective_policy(policy_map(db, fid), uid)['rates'].get(key)
    if branch_id:
        from app.services.receipt_commissions import effective_branch_rates
        own=effective_branch_rates(db,fid,uid,permission_branch(db,fid,uid,branch_id)).get(key)
        if own is not None: rate=own
    if rate is None and category in MANUAL_TYPES - {'overtime'}:
        row = db.execute(text('SELECT rate FROM commission_structures WHERE franchise_user_id=:fid AND commission_type=:type AND is_active=TRUE'), {'fid': fid, 'type': category}).mappings().first()
        rate = row['rate'] if row else None
    if rate is None:
        raise HTTPException(400, 'The franchise holder must configure this Employee/Assistant fee under Business → Commissions.')
    return money(rate)


def assert_unique_case(db, fid, uid, category, branch, reference, exclude_id=None):
    rows = db.execute(text('''SELECT id,reference FROM commission_entries WHERE franchise_user_id=:fid
        AND employee_user_id=:uid AND commission_type=:type AND earning_branch_id=:branch
        AND COALESCE(is_cancelled,FALSE)=FALSE AND status<>'cancelled' '''), {'fid': fid, 'uid': uid, 'type': category, 'branch': branch}).mappings().all()
    if any(r['id'] != exclude_id and mf_key(r['reference'].split(' / Invoice ', 1)[0].split(' / Receipt ', 1)[0]) == mf_key(reference) for r in rows):
        raise HTTPException(409, 'This staff member already has this commission item for this MF case. Repeated claims or dates do not increase the service count.')


def surcharge_line(db, user, fid, uid, role, branch_id, proof, day, reference):
    branch = db.execute(text('SELECT name FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid'), {'id': branch_id, 'fid': fid}).scalar()
    if not branch or not is_external(db, fid, branch_id) or not outside_group(db, fid, branch):
        return None
    category = 'service_other_branch'
    bid = permission_branch(db, fid, uid, branch_id)
    if not enabled_for_branch(db, fid, uid, category, bid):
        return None
    existing = db.execute(text("SELECT id FROM commission_entries WHERE franchise_user_id=:fid AND employee_user_id=:uid AND commission_type='service_other_branch' AND invoice_document_id=:invoice AND status<>'cancelled'"), {'fid': fid, 'uid': uid, 'invoice': proof['invoice_document_id']}).scalar()
    if existing:
        return None
    rate = fixed_rate(db, fid, uid, category, role, branch_id)
    return {**proof, 'mf': mf_key(reference), 'branch': branch, 'reference': reference, 'employee_user_id': uid,
            'category': category, 'earning_branch_id': branch_id, 'service_date': str(day), 'role': role,
            'amount': str(rate), 'rate': str(rate), 'state': 'ready', 'reason': '', 'calculation_type': 'fixed'}


def insert_surcharge(db, user, line):
    from app.api.commission import _audit, _notify
    fid = db.execute(text('SELECT franchise_user_id FROM attendance_branches WHERE id=:id'), {'id': line['earning_branch_id']}).scalar_one()
    row = db.execute(text('''INSERT INTO commission_entries(franchise_user_id,employee_user_id,commission_type,service_date,
        reference,quantity,applied_rate,calculated_amount,branch_name,created_by_user_id,status,submitted_at,reviewed_at,
        reviewed_by_user_id,last_edited_by_user_id,mortuary_document_id,receipt_document_id,invoice_document_id,source_metadata,earning_branch_id)
        VALUES(:fid,:uid,'service_other_branch',:day,:ref,1,:rate,:rate,:branch,:actor,'approved',NOW(),NOW(),:actor,:actor,:book,:receipt,:invoice,:meta,:bid) RETURNING *'''),
        {'fid': fid, 'uid': line['employee_user_id'], 'day': line['service_date'], 'ref': line['reference'], 'rate': Decimal(line['rate']), 'branch': line['branch'], 'actor': user.id,
         'book': line['mortuary_document_id'], 'receipt': line['receipt_document_id'], 'invoice': line['invoice_document_id'], 'meta': json.dumps(line, default=str), 'bid': line['earning_branch_id']}).mappings().first()
    _audit(db, row['id'], 'external_branch_additional_fee', user.id, new=dict(row))
    _notify(db, line['employee_user_id'], 'Outside branch commission approved', f"Additional fee for MF {line['reference']}.", row['id'], 'success')
    return row['id']


def calculate_claim(db, user, payload, participant, exclude_id=None):
    if payload.commission_type not in CLAIM_TYPES:
        raise HTTPException(400, 'Choose an enabled commission item. The outside-branch fee is added automatically when enabled.')
    if payload.rate_override is not None or Decimal(payload.quantity) != 1:
        raise HTTPException(400, 'Each claim is for one MF case and uses the configured rate. Rate overrides and multiplied quantities are not allowed.')
    if not str(payload.claim_deceased or '').strip():
        raise HTTPException(400, 'Enter the deceased’s name and surname exactly as printed on the documents.')
    fid, uid = participant['franchise_user_id'], participant['user_id']
    branch = require_manual_eligibility(db, participant, payload.commission_type, payload.earning_branch_id)
    name = db.execute(text('SELECT name FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid AND is_active=TRUE'), {'id': branch, 'fid': fid}).scalar()
    if not name:
        raise HTTPException(403, 'Service branch is outside the selected holder’s declared scope.')
    assert_unique_case(db, fid, uid, payload.commission_type, branch, payload.reference, exclude_id)
    rate, amount, calculation_type, estimate_notice, details = claim_amount(db, fid, uid, payload, participant, branch)
    proof, reason, extra = {}, estimate_notice, None
    try:
        proof = require_payment_proof(db, fid, branch, payload.reference)
        if normalise(payload.claim_deceased) != normalise(proof['deceased']):
            raise HTTPException(400, 'The claim’s deceased name and surname do not match the imported documents.')
        if estimate_notice:
            raise HTTPException(400, estimate_notice)
        extra = surcharge_line(db, user, fid, uid, payload.commission_role, branch, proof, payload.service_date, payload.reference)
    except HTTPException as exc:
        if exc.status_code not in (400, 409):
            raise
        reason = exc.detail
    return {**details, 'rate': str(rate), 'amount': str(amount), 'calculation_type': calculation_type,
            'estimate_available': estimate_notice is None, 'branch_id': branch, 'branch_name': name,
            'documents_valid': reason is None, 'notice': reason, 'proof': proof,
            'additional_fee': extra, 'claim_deceased': payload.claim_deceased, 'commission_role': payload.commission_role}


def claim_amount(db, fid, uid, payload, participant, branch):
    """Read rates and evidence on the server; uploads never choose recipients."""
    category = payload.commission_type
    if category in MANUAL_TYPES:
        fee = fixed_rate(db, fid, uid, category, payload.commission_role, branch)
        return fee, fee, 'fixed', None, {}
    from app.api.mortuary import policy_map
    from app.services.receipt_commissions import branch_key, invoice_commission_rate, resolve_commission_vat
    docs = db.execute(text('''SELECT id,kind,source_data FROM commission_documents
        WHERE franchise_user_id=:fid AND branch_key=:branch AND mf_key=:mf AND deleted_at IS NULL'''),
        {'fid':fid, 'branch':branch_key(db.execute(text('SELECT name FROM attendance_branches WHERE id=:id'), {'id':branch}).scalar()),
         'mf':mf_key(payload.reference)}).mappings().all()
    if category == 'invoice_commission':
        from app.api.receipt_commissions import receipt_settings
        rate = invoice_commission_rate(db,fid,uid,payload.commission_role,branch,policy_map(db,fid),receipt_settings(db,fid,branch))
        if rate is None:
            raise HTTPException(400, 'The holder must configure this employee’s invoice commission percentage.')
        invoices = [d for d in docs if d['kind']=='invoice']
        if len(invoices)!=1:
            return Decimal(str(rate)), Decimal(0), 'percentage', 'Upload one matching MF Invoice before the percentage amount can be calculated.', {}
        try:
            base = resolve_commission_vat(db,fid,branch,json.loads(invoices[0]['source_data']))['commission_base']
        except HTTPException as exc:
            return Decimal(str(rate)), Decimal(0), 'percentage', exc.detail, {}
        return Decimal(str(rate)), money(Decimal(base)*Decimal(str(rate))/100), 'percentage', None, {}
    books = [d for d in docs if d['kind']=='mortuary']
    if len(books)!=1:
        return Decimal(0), Decimal(0), 'fixed', 'Upload the matching Mortuary Book to verify removal staff and calculate the fee.', {}
    record = json.loads(books[0]['source_data'])
    # Match printed names uniquely against active staff; a claim cannot assign
    # someone else's removal or change a two-person removal's printed role.
    from app.services.attendance_branches import import_staff
    from app.services.mortuary import match_employee
    people = import_staff(db,fid)
    matches = [match_employee(name,people) for name in record.get('names',[])]
    if uid not in matches or matches.count(uid)!=1:
        return Decimal(0), Decimal(0), 'fixed', 'The claimant is not uniquely identified in the Mortuary Book removal staff. Correct the staff name or document for review.', {}
    printed_name = record['names'][matches.index(uid)]
    expected_role = 'driver' if len(matches)==1 or normalise(printed_name)==normalise(record.get('driver')) else 'assistant'
    if payload.commission_role!=expected_role:
        return Decimal(0), Decimal(0), 'fixed', 'The removal role must match the printed Driver and Driver In details in the Mortuary Book.', {}
    from app.services.pending_removals import removal_estimate
    person = next(p for p in people if p['user_id']==uid)
    try:
        fee = removal_estimate(db,fid,uid,record,expected_role,person,policy_map(db,fid),branch)
    except (ValueError, TypeError):
        raise HTTPException(400, 'Correct this staff member’s business hours before calculating the removal fee.')
    if fee['amount'] is None:
        raise HTTPException(400, 'The holder must configure this removal fee under Business → Commissions.')
    return Decimal(fee['amount']), Decimal(fee['amount']), 'fixed', None, fee

