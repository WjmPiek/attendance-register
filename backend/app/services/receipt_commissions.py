"""Receipt extraction, opt-in rules and VAT-inclusive payment arithmetic."""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import json
import re

from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import text
from pydantic import BaseModel, Field

from app.services.mortuary import normalise

class CommissionBranchOptions(BaseModel):
    enabled_types: list[str] = Field(default_factory=list, max_length=9)
    receipt_percentage: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=4)
    inherit_home: bool = False
    rates: dict[str, Decimal | None] = Field(default_factory=dict)


COMMISSION_LABELS = {
    'removals': 'Removals', 'invoice_commission': 'MF File Receipts',
    'grave_service': 'Grave Service', 'full_funeral_service': 'Full Funeral Service',
    'cremation_service': 'Cremation Service', 'church_service': 'Church Service',
    'joinings': 'Joinings', 'overtime': 'Overtime',
    'service_other_branch': 'Service for Other Branch (additional fee)',
}


def mf_key(value):
    return re.sub(r'[^A-Z0-9]', '', re.sub(r'^MF[\s-]*', '', str(value).strip(), flags=re.I).upper())


def branch_key(value):
    value = re.sub(r'\s*\((?:F|C)\)\s*$', '', value or '', flags=re.I)
    return ' '.join(w for w in normalise(value).split() if w not in {'martin', 'martins', 's', 'funeral', 'funerals'})


def money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def printed_money(value):
    value = re.sub(r'\s+', '', value)
    if ',' in value and '.' not in value and re.fullmatch(r'\d+,\d{2}', value):
        value = value.replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?', value):
        value = value.replace(',', '')
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?', value):
        raise ValueError('Unrecognised payment amount format.')
    amount = money(value)
    if amount > Decimal('9999999999.99'):
        raise ValueError('Payment amount exceeds the supported range.')
    return amount


def receipt_base(gross, registered, vat_rate):
    if registered is None:
        raise ValueError('Confirm franchise VAT registration status first.')
    gross = Decimal(str(gross))
    return money(gross / (1 + Decimal(str(vat_rate)) / 100)) if registered else money(gross)


def parse_receipt_text(value):
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    lines = [' '.join(x.split()) for x in value.splitlines() if x.strip()]
    if not re.search(r'\bRECEIPT\b', value, re.I):
        raise ValueError('This page is not an MF File Receipt.')
    def field(pattern):
        result = re.search(pattern, value, re.I | re.M)
        return result.group(1).strip() if result else ''
    record = {
        'reference': field(r'^MF\s*(?:No\.?|Number)\s*[:.]?\s*(.+)$'),
        'receipt_number': field(r'^Receipt\s*(?:Nr\.?|No\.?)\s*[:.]?\s*(.+)$'),
        'invoice_number': field(r'^Inv\s*No\.?\s*[:.]?\s*(.+)$'),
        'deceased': field(r'^Deceased\s*:\s*(.+)$'),
        'id_number': field(r'^ID\s*Num(?:ber)?\s*:\s*(.+)$'),
        'service_date': field(r'^Date\s+(.+)$'),
        'gross_received': field(r'^(?:Amnt\s*Rcvd|Amount\s*Received|Total\s*Received)\s*:\s*R?\s*([\d, .]+)$'),
    }
    # A long deceased name wraps above the ID label in the printed receipt.
    # Read only this bounded field, never the purchaser printed after the ID.
    wrapped = re.search(r'^Deceased[ \t]*:[ \t]*([^\r\n]+(?:\r?\n[^\r\n]+)*?)\r?\n[ \t]*ID[ \t]+Num(?:ber)?[ \t]*:', value, re.I | re.M)
    if wrapped:
        parts = wrapped.group(1).splitlines()
        if all(part.strip() and ':' not in part for part in parts):
            record['deceased'] = ' '.join(' '.join(parts).split())
    # The print template puts the franchise immediately below MARTINS FUNERALS.
    headings = [i for i, line in enumerate(lines) if line.upper() == 'MARTINS FUNERALS']
    record['branch'] = lines[headings[0] + 1] if headings and headings[0] + 1 < len(lines) else ''
    if not record['branch']:
        match = re.search(r'^MARTINS FUNERALS\s+(.+)$', value, re.I | re.M)
        record['branch'] = match.group(1).strip() if match else ''
    for key in ('reference', 'receipt_number', 'service_date', 'gross_received', 'branch', 'deceased'):
        if not record[key]:
            raise ValueError('Required receipt field missing: ' + key.replace('_', ' '))
    if any(len(record[k]) > 255 for k in ('reference', 'receipt_number', 'branch')):
        raise ValueError('Receipt reference or branch is too long.')
    for fmt in ('%d-%b-%y', '%d-%b-%Y', '%d %b %Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            record['service_date'] = datetime.strptime(record['service_date'], fmt).date().isoformat()
            break
        except ValueError:
            pass
    else:
        raise ValueError('Unrecognised receipt date.')
    record['gross_received'] = str(printed_money(record['gross_received']))
    if Decimal(record['gross_received']) <= 0:
        raise ValueError('Amount received must be positive; refunds require separate review.')
    return record


def parse_receipt_pdf(data):
    if not data.lstrip().startswith(b'%PDF-'):
        raise ValueError('Upload a PDF file.')
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 50:
        raise ValueError('Use an unprotected PDF with 1–50 pages.')
    from app.services.pdf_records import parse_document_pages
    return parse_document_pages(reader, parse_receipt_text, 'receipt')


def option_map(db, fid, uid):
    return {r['commission_type']: dict(r) for r in db.execute(text('''SELECT commission_type,enabled,rate
        FROM employee_commission_options WHERE franchise_user_id=:fid AND employee_user_id=:uid'''),
        {'fid': fid, 'uid': uid}).mappings().all()}


def enabled(db, fid, uid, category):
    return bool(option_map(db, fid, uid).get(category, {}).get('enabled'))


def branch_options(db, fid, uid):
    result = {}
    rows = db.execute(text('''SELECT o.branch_id,o.commission_type,o.rate FROM employee_commission_branch_options o
        JOIN attendance_branches b ON b.id=o.branch_id AND b.franchise_user_id=o.franchise_user_id
        WHERE o.franchise_user_id=:fid AND o.employee_user_id=:uid AND b.is_active=TRUE
        ORDER BY o.branch_id,o.commission_type'''), {'fid':fid,'uid':uid}).mappings().all()
    for row in rows:
        group = result.setdefault(str(row['branch_id']), {'enabled_types':[], 'receipt_percentage':None})
        group['enabled_types'].append(row['commission_type'])
        if row['commission_type']=='invoice_commission':
            group['receipt_percentage']=row['rate']
    from app.services.attendance_branches import assignment, branches
    home=assignment(db,uid)
    if not home or home['franchise_user_id']!=fid or not home['branch_active']:
        return {}
    overrides={str(r['branch_id']):json.loads(r['rates']) for r in db.execute(text('SELECT branch_id,rates FROM employee_commission_branch_overrides WHERE franchise_user_id=:fid AND employee_user_id=:uid'), {'fid':fid,'uid':uid}).mappings()}
    home_key=str(home['branch_id'])
    base=result.get(home_key,{'enabled_types':[],'receipt_percentage':None})
    effective={}
    for branch in branches(db,fid):
        key=str(branch['id']);inherit=key!=home_key and key not in overrides
        own=result.get(key,{'enabled_types':[],'receipt_percentage':None})
        effective[key]={**(base if inherit else own),'inherit_home':inherit,'home_branch_id':home['branch_id'],
                        'rates':overrides.get(home_key,{}) if inherit else overrides.get(key,{})}
    return effective


def enabled_for_branch(db, fid, uid, category, branch_id):
    return enabled(db, fid, uid, category) and category in branch_options(db,fid,uid).get(str(branch_id),{}).get('enabled_types',[])


def effective_branch_rates(db,fid,uid,branch_id):
    values=branch_options(db,fid,uid)
    selected=values.get(str(branch_id),{})
    home=values.get(str(selected.get('home_branch_id')),{})
    return {**home.get('rates',{}),**selected.get('rates',{})}


def save_branch_options(db, fid, uid, values, actor, *, branch_id=None):
    from app.services.attendance_branches import branches
    available = {b['id'] for b in branches(db,fid)}
    normalised = {int(key):(value.model_dump() if hasattr(value,'model_dump') else CommissionBranchOptions(**value).model_dump()) for key,value in values.items()}
    if set(normalised)-available:
        raise HTTPException(403,'Commission branch is outside this holder group.')
    if branch_id is not None and set(normalised) != {branch_id}:
        raise HTTPException(400, 'Supply commission settings for the selected branch only.')
    all_types = set()
    for value in normalised.values():
        if not value.get('inherit_home'): all_types.update(value.get('enabled_types',[]))
    if all_types-set(COMMISSION_LABELS):
        raise HTTPException(400,'Invalid commission category.')
    from app.api.mortuary import Rates
    from pydantic import ValidationError
    for value in normalised.values():
        if set(value.get('rates',{}))-set(Rates.model_fields): raise HTTPException(400,'Unknown branch commission rate.')
        try: value['rates']=Rates(**value.get('rates',{})).model_dump(mode='json',exclude_none=True)
        except ValidationError: raise HTTPException(422,'Branch fees must be valid non-negative amounts; commission percentages must be between 0 and 100.')
    from app.services.attendance_branches import assignment
    home=assignment(db,uid)
    if home and normalised.get(home['branch_id'],{}).get('inherit_home'):
        raise HTTPException(400,'The home branch must have its own commission settings.')
    # A branch editor must never replace another branch's permissions or fees,
    # even if that other branch was changed after the editor was opened.
    scope = ' AND branch_id=:branch' if branch_id is not None else ''
    params = {'fid':fid, 'uid':uid, 'branch':branch_id}
    db.execute(text('DELETE FROM employee_commission_branch_options WHERE franchise_user_id=:fid AND employee_user_id=:uid' + scope), params)
    db.execute(text('DELETE FROM employee_commission_branch_overrides WHERE franchise_user_id=:fid AND employee_user_id=:uid' + scope), params)
    for bid,value in normalised.items():
        if value.get('inherit_home'):
            if home and bid==home['branch_id']: raise HTTPException(400,'The home branch must have its own commission settings.')
            continue
        from app.api.mortuary import Rates
        if set(value.get('rates',{}))-set(Rates.model_fields): raise HTTPException(400,'Unknown branch commission rate.')
        rates=value['rates']
        db.execute(text('INSERT INTO employee_commission_branch_overrides(franchise_user_id,employee_user_id,branch_id,rates) VALUES(:fid,:uid,:branch,:rates)'), {'fid':fid,'uid':uid,'branch':bid,'rates':json.dumps(rates)})
        for category in set(value.get('enabled_types',[])):
            db.execute(text('''INSERT INTO employee_commission_branch_options(franchise_user_id,employee_user_id,commission_type,branch_id,rate)
                VALUES(:fid,:uid,:type,:branch,:rate)'''), {'fid':fid,'uid':uid,'type':category,'branch':bid,
                'rate':value.get('receipt_percentage') if category=='invoice_commission' else None})
    # Global flags are the union of saved grants, not just the branch being
    # edited. Branch eligibility still checks the selected branch separately.
    saved_types = db.execute(text('''SELECT DISTINCT o.commission_type FROM employee_commission_branch_options o
        JOIN attendance_branches b ON b.id=o.branch_id AND b.franchise_user_id=o.franchise_user_id
        WHERE o.franchise_user_id=:fid AND o.employee_user_id=:uid AND b.is_active=TRUE'''), params).scalars().all()
    set_enabled_types(db,fid,uid,saved_types,actor)


def set_enabled_types(db, fid, uid, types, actor):
    if set(types) - set(COMMISSION_LABELS):
        raise HTTPException(400, 'Invalid employee commission category.')
    for category in COMMISSION_LABELS:
        db.execute(text('''INSERT INTO employee_commission_options(franchise_user_id,employee_user_id,commission_type,enabled,updated_by_user_id)
            VALUES(:fid,:uid,:type,:enabled,:actor) ON CONFLICT(franchise_user_id,employee_user_id,commission_type)
            DO UPDATE SET enabled=EXCLUDED.enabled,updated_by_user_id=EXCLUDED.updated_by_user_id,updated_at=NOW()'''),
            {'fid': fid, 'uid': uid, 'type': category, 'enabled': category in types, 'actor': actor})


def require_manual_eligibility(db, participant, category, branch_id=None):
    from app.services.attendance_branches import assignment
    home = assignment(db, participant['user_id'])
    if not home or not home['branch_active'] or home['franchise_user_id'] != participant['franchise_user_id']:
        raise HTTPException(403, 'Employee must belong to an active branch in this holder group.')
    if not enabled(db, participant['franchise_user_id'], participant['user_id'], category):
        raise HTTPException(403, 'This commission category is not enabled for this employee.')
    branch_id = branch_id or home['branch_id']
    from app.services.external_commissions import permission_branch
    scope_branch = permission_branch(db, participant['franchise_user_id'], participant['user_id'], branch_id)
    if not enabled_for_branch(db,participant['franchise_user_id'],participant['user_id'],category,scope_branch):
        raise HTTPException(403,'This commission is not enabled for this employee at the selected branch.')
    return branch_id


def invoice_commission_rate(db, fid, uid, role, branch_id, policies, settings):
    from app.api.mortuary import effective_policy
    from app.services.external_commissions import permission_branch
    selected=permission_branch(db,fid,uid,branch_id)
    preference=branch_options(db,fid,uid).get(str(selected),{})
    options=option_map(db,fid,uid)
    candidates=[preference.get('rates',{}).get(f'{role}_invoice_commission'),preference.get('receipt_percentage'),
                effective_branch_rates(db,fid,uid,selected).get(f'{role}_invoice_commission'),
                policies.get(uid,{}).get('rates',{}).get(f'{role}_invoice_commission'),
                options.get('invoice_commission',{}).get('rate'),
                effective_policy(policies,uid)['rates'].get(f'{role}_invoice_commission'),settings.get('receipt_percentage')]
    return next((rate for rate in candidates if rate is not None),None)


def resolve_commission_vat(db, fid, branch_id, invoice):
    """A signed main-system VAT record overrides invoice and local VAT settings."""
    branch = db.execute(text('SELECT vat_number,main_synced FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid'), {'id': branch_id, 'fid': fid}).mappings().first()
    settings = db.execute(text('SELECT * FROM receipt_commission_settings WHERE franchise_user_id=:fid AND branch_id IN (0,:branch) ORDER BY branch_id DESC'), {'fid': fid, 'branch': branch_id}).mappings().all()
    direct = next((r for r in settings if r['branch_id'] == branch_id), None)
    inherited = next((r for r in settings if r['branch_id'] == 0), None)
    recorded_number = str((branch or {}).get('vat_number') or '').strip()
    registered, number, source = None, None, None
    from app.services.external_commissions import is_external
    if is_external(db, fid, branch_id):
        inherited = None
    configuration = direct or inherited
    if recorded_number:
        if not re.fullmatch(r'\d{10}', recorded_number):
            raise HTTPException(400, 'The system branch VAT number is invalid. Correct its registration record before approval.')
        registered, number, source = True, recorded_number, 'System branch VAT registration'
    elif branch and branch['main_synced']:
        registered, number, source = False, None, 'Main system: not VAT registered'
    elif direct:
        registered, number, source = bool(direct['vat_registered']), direct.get('vat_number'), 'Confirmed branch VAT settings'
    elif inherited and not inherited['vat_registered']:
        registered, source = False, 'Confirmed holder non-VAT settings'
    valid_print = invoice.get('vat_issue') is None and isinstance(invoice.get('vat_registered'), bool) and invoice.get('commission_base') is not None
    if registered is None:
        if not valid_print:
            raise HTTPException(400, 'Invoice VAT details are unclear and the system has no confirmed branch VAT status. Confirm it under Business → Commission Rates.')
        registered, number, source = invoice['vat_registered'], invoice.get('vat_number'), 'Printed invoice VAT details'
    total = Decimal(str(invoice['invoice_total']))
    rate = Decimal(str(configuration['vat_rate'] if configuration else invoice.get('vat_rate') if valid_print and invoice['vat_registered'] else 15)) if registered else Decimal(0)
    if registered and (not number or not re.fullmatch(r'\d{10}', str(number)) or not rate.is_finite() or not 0 <= rate <= 100):
        raise HTTPException(400, 'Confirm a valid branch VAT registration number and VAT rate in the system.')
    compatible = valid_print and invoice['vat_registered'] == registered and (not registered or str(invoice.get('vat_number')) == str(number)) and (not registered or Decimal(str(invoice.get('vat_rate', 0))) == rate)
    base = Decimal(str(invoice['commission_base'])) if compatible and registered else receipt_base(total, registered, rate)
    if not base.is_finite() or base < 0 or base > total:
        raise HTTPException(400, 'Invoice commission base is inconsistent with its total.')
    return {'commission_base': str(base), 'vat_registered': registered, 'vat_number': number, 'vat_rate': str(rate),
            'vat_source': source, 'vat_notice': None if compatible else 'Printed VAT details were resolved using the confirmed system branch VAT record.'}


def require_payment_proof(db, fid, branch_id, reference, book_id=None, receipt_id=None, invoice_id=None):
    """Require a fully paid invoice and exact identity across imported evidence."""
    branch = db.execute(text('SELECT name FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid'),
                        {'id': branch_id, 'fid': fid}).scalar()
    if not branch:
        raise HTTPException(400, 'Select the commission branch before checking payment proof.')
    reference = str(reference or '')
    if book_id and receipt_id:
        reference = reference.split(' / Receipt ', 1)[0].split(' / Invoice ', 1)[0]
    docs = db.execute(text('''SELECT id,kind,source_data FROM commission_documents
        WHERE franchise_user_id=:fid AND branch_key=:branch AND mf_key=:mf AND deleted_at IS NULL ORDER BY id'''),
        {'fid': fid, 'branch': branch_key(branch), 'mf': mf_key(reference)}).mappings().all()
    books = [d for d in docs if d['kind'] == 'mortuary' and (not book_id or d['id'] == book_id)]
    invoices = [d for d in docs if d['kind'] == 'invoice' and (not invoice_id or d['id'] == invoice_id)]
    receipts = [d for d in docs if d['kind'] == 'receipt']
    if not books or not receipts or len(invoices) != 1:
        raise HTTPException(400, 'Matching Mortuary Book, MF Invoice and MF File Receipts are compulsory before any commission can be approved for payment. Import all three for this branch and MF number.')
    invoice = invoices[0]
    invoice_data = json.loads(invoice['source_data'])
    invoice_number = normalise(invoice_data.get('invoice_number'))
    deceased = normalise(invoice_data.get('deceased'))
    total = Decimal(str(invoice_data.get('invoice_total', '0')))
    if not deceased or not invoice_number or not total.is_finite() or total <= 0:
        raise HTTPException(400, 'Invoice must identify the deceased, invoice number and a positive total.')
    tax = resolve_commission_vat(db, fid, branch_id, invoice_data)
    book = books[0]
    book_data = json.loads(book['source_data'])
    if not normalise(book_data.get('deceased')) or normalise(book_data.get('deceased')) != deceased:
        raise HTTPException(400, 'Deceased name and surname must match on the Mortuary Book, MF Invoice and every payment receipt.')
    identities = {str(d.get('id_number')).strip() for d in (book_data, invoice_data) if d.get('id_number')}
    paid, seen, included = Decimal(0), set(), []
    for receipt in receipts:
        data = json.loads(receipt['source_data'])
        if normalise(data.get('invoice_number')) != invoice_number:
            raise HTTPException(400, 'Receipt invoice number does not match the MF Invoice. Check the payment evidence.')
        if not normalise(data.get('deceased')) or normalise(data.get('deceased')) != deceased:
            raise HTTPException(400, 'Deceased name and surname must match on all three document types.')
        if data.get('id_number'):
            identities.add(str(data['id_number']).strip())
        number = normalise(data.get('receipt_number'))
        amount = Decimal(str(data.get('gross_received', '0')))
        if not number or not amount.is_finite() or amount <= 0:
            raise HTTPException(400, 'Each payment receipt must have its own receipt number and a positive amount received.')
        if number in seen:
            raise HTTPException(400, 'Repeated receipt numbers cannot count as additional payments.')
        seen.add(number); included.append(receipt['id']); paid += amount
    if len(identities) > 1:
        raise HTTPException(400, 'MF matches but deceased ID numbers differ across the documents.')
    if receipt_id and receipt_id not in included:
        raise HTTPException(400, 'The linked receipt is outside this invoice payment evidence.')
    if paid < total:
        raise HTTPException(400, f'Invoice not fully paid: received R {paid:,.2f} of R {total:,.2f}. No commission is payable until the balance is settled.')
    if paid > total:
        raise HTTPException(400, f'Receipts exceed the invoice: received R {paid:,.2f} against R {total:,.2f}. Correct the payment evidence before commission is allocated.')
    return {'mortuary_document_id': book['id'], 'receipt_document_id': included[0], 'invoice_document_id': invoice['id'],
            'invoice_total': str(total), 'total_received': str(paid), 'invoice_number': invoice_data['invoice_number'],
            'receipt_document_ids': included, 'deceased': invoice_data['deceased'], **tax}


def payment_eligibility(db, row):
    try:
        meta = json.loads(row.get('source_metadata') or '{}')
        if row.get('status')=='pending' and meta.get('mf_case_claim'):
            from app.services.case_claims import quote_case_item
            try:
                _,quote=quote_case_item(db,{'user_id':row['employee_user_id'],'franchise_user_id':row['franchise_user_id']},row['earning_branch_id'],row['reference'],row['commission_type'],exclude_id=row['id'])
                return {'payment_eligible':quote['documents_valid'],'payment_block_reason':quote['notice'],'expected_amount':quote['amount'],
                        'estimate_available':quote['estimate_available'],'earning_branch_id':quote['branch_id'],'branch_name':quote['branch_name'],
                        'expected_additional_fee':quote['additional_fee']['amount'] if quote['additional_fee'] else '0'}
            except HTTPException as exc:
                return {'payment_eligible':False,'payment_block_reason':exc.detail,'expected_amount':'0','estimate_available':False}
        if row.get('status') == 'pending' and meta.get('claim_deceased'):
            from app.api.commission import EntryIn
            from app.services.service_claims import calculate_claim
            values = {key: row[key] for key in EntryIn.model_fields if key in row}
            values.update(claim_deceased=meta['claim_deceased'], commission_role=meta.get('commission_role', 'driver'))
            quote = calculate_claim(db, None, EntryIn(**values), {'user_id': row['employee_user_id'], 'franchise_user_id': row['franchise_user_id']}, exclude_id=row['id'])
            return {'payment_eligible': quote['documents_valid'], 'payment_block_reason': quote['notice'], 'expected_amount': quote['amount'],
                    'expected_additional_fee': quote['additional_fee']['amount'] if quote['additional_fee'] else '0',
                    'expected_invoice_id': quote['proof'].get('invoice_document_id'), 'estimate_available':quote['estimate_available']}
        require_payment_proof(db, row['franchise_user_id'], row.get('earning_branch_id'), row['reference'],
                              row.get('mortuary_document_id'), row.get('receipt_document_id'), row.get('invoice_document_id'))
        return {'payment_eligible': True, 'payment_block_reason': None}
    except HTTPException as exc:
        return {'payment_eligible': False, 'payment_block_reason': exc.detail}

