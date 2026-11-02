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
    enabled_types: list[str] = Field(default_factory=list, max_length=8)
    receipt_percentage: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=4)


COMMISSION_LABELS = {
    'removals': 'Removals', 'invoice_commission': 'MF File Receipts',
    'grave_service': 'Grave Service', 'full_funeral_service': 'Full Funeral Service',
    'cremation_service': 'Cremation Service', 'church_service': 'Church Service',
    'joinings': 'Joinings', 'overtime': 'Overtime',
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
    records, errors = [], []
    for n, page in enumerate(reader.pages):
        try:
            record = parse_receipt_text(page.extract_text() or '')
            record['page'] = n + 1
            records.append(record)
        except (ValueError, TypeError) as exc:
            errors.append({'page': n + 1, 'error': str(exc)})
    return records, errors


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
    return result


def enabled_for_branch(db, fid, uid, category, branch_id):
    return enabled(db, fid, uid, category) and category in branch_options(db,fid,uid).get(str(branch_id),{}).get('enabled_types',[])


def save_branch_options(db, fid, uid, values, actor):
    from app.services.attendance_branches import branches
    available = {b['id'] for b in branches(db,fid)}
    normalised = {int(key):(value.model_dump() if hasattr(value,'model_dump') else CommissionBranchOptions(**value).model_dump()) for key,value in values.items()}
    if set(normalised)-available:
        raise HTTPException(403,'Commission branch is outside this holder group.')
    all_types = set()
    for value in normalised.values():
        all_types.update(value.get('enabled_types',[]))
    if all_types-set(COMMISSION_LABELS):
        raise HTTPException(400,'Invalid commission category.')
    set_enabled_types(db,fid,uid,list(all_types),actor)
    db.execute(text('DELETE FROM employee_commission_branch_options WHERE franchise_user_id=:fid AND employee_user_id=:uid'), {'fid':fid,'uid':uid})
    for bid,value in normalised.items():
        for category in set(value.get('enabled_types',[])):
            db.execute(text('''INSERT INTO employee_commission_branch_options(franchise_user_id,employee_user_id,commission_type,branch_id,rate)
                VALUES(:fid,:uid,:type,:branch,:rate)'''), {'fid':fid,'uid':uid,'type':category,'branch':bid,
                'rate':value.get('receipt_percentage') if category=='invoice_commission' else None})


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
    if category in {'removals', 'invoice_commission'}:
        raise HTTPException(400, 'Use the matched Mortuary Book and MF File Receipt imports for this commission category.')
    branch_id = branch_id or home['branch_id']
    if not enabled_for_branch(db,participant['franchise_user_id'],participant['user_id'],category,branch_id):
        raise HTTPException(403,'This commission is not enabled for this employee at the selected branch.')
    return branch_id
