"""Stage receipt evidence, then approve only paired, opted-in commissions."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from itsdangerous import BadSignature
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.commission import _participant, _audit, _notify, employees, _assert_not_duplicate, EntryIn
from app.api.deps import get_current_user
from app.api.franchise_staff import _staff_franchise_id
from app.api.mortuary import signer, policy_map, effective_policy
from app.db.session import get_db
from app.models.core import User
from app.services.mortuary import price_removal
from app.services.receipt_commissions import (
    COMMISSION_LABELS, branch_key, mf_key, money, option_map, enabled,
    parse_receipt_pdf, receipt_base, set_enabled_types,
)
from app.services.audit import write_audit_log

from app.services.attendance_branches import import_scope, import_staff, import_participant, branches, assignment

router = APIRouter()


class OptionIn(BaseModel):
    employee_user_id: int
    franchise_user_id: int | None = None
    enabled_types: list[str] = Field(max_length=8)
    receipt_percentage: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=4)


class SettingsIn(BaseModel):
    branch_id: int = Field(default=0, ge=0)
    franchise_user_id: int | None = None
    vat_registered: bool
    vat_number: str | None = Field(default=None, max_length=100)
    vat_rate: Decimal = Field(default=15, ge=0, le=100, decimal_places=4)
    receipt_percentage: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=4)

    @model_validator(mode='after')
    def registration(self):
        if self.vat_registered and (not self.vat_number or not self.vat_number.strip().isdigit() or len(self.vat_number.strip()) != 10):
            raise ValueError('Enter the franchise VAT registration number (10 digits) when registered.')
        return self


class ReceiptAllocation(BaseModel):
    record: int = Field(ge=0)
    employee_user_ids: list[int] = Field(max_length=100)


class StageIn(BaseModel):
    preview_token: str = Field(max_length=2000000)
    allocations: list[ReceiptAllocation] = Field(max_length=100)
    confirmed_franchise: bool = False


class CalculateIn(BaseModel):
    franchise_user_id: int | None = None
    document_ids: list[int] = Field(min_length=1, max_length=100)
    quote_token: str | None = Field(default=None, max_length=2000000)


def franchise_record(db, fid):
    return db.execute(text('SELECT id,franchise_name,business_name,trading_as,vat_number FROM franchise_users WHERE id=:fid AND COALESCE(is_active,TRUE)=TRUE'), {'fid': fid}).mappings().first()


def require_branch(db, fid, value):
    franchise = franchise_record(db, fid)
    available = branches(db, fid)
    aliases = {branch_key(b['name']) for b in available}
    if not available:
        aliases = {branch_key(franchise.get(k) or '') for k in ('franchise_name', 'business_name', 'trading_as')} if franchise else set()
    if sum(branch_key(b['name']) == branch_key(value) for b in available) > 1:
        raise HTTPException(400, 'Printed branch name is ambiguous within this holder group. Use distinct branch names before importing.')
    if not branch_key(value) or branch_key(value) not in aliases:
        raise HTTPException(400, f'Printed franchise "{value}" does not match this franchise profile. Correct the franchise profile or use its own document.')


def receipt_settings(db, fid, branch_id=0):
    row = db.execute(text('SELECT * FROM receipt_commission_settings WHERE franchise_user_id=:fid AND branch_id=:branch'), {'fid': fid, 'branch': branch_id}).mappings().first()
    default = receipt_settings(db, fid, 0) if branch_id else None
    if row:
        result = dict(row)
        result['vat_registered'] = bool(result['vat_registered'])
        if branch_id and result.get('receipt_percentage') is None:
            result['receipt_percentage'] = default.get('receipt_percentage')
        return result
    if branch_id:
        branch = next((b for b in branches(db, fid) if b['id'] == branch_id), None)
        if not branch:
            raise HTTPException(403, 'Branch is outside this holder group.')
        recorded_number = str(branch.get('vat_number') or '').strip()
        conflicting_number = recorded_number and (not bool(default.get('vat_registered')) or recorded_number != str(default.get('vat_number') or '').strip())
        unconfirmed_group_vendor = len(branches(db, fid)) > 1 and bool(default.get('vat_registered')) and not recorded_number
        if conflicting_number or unconfirmed_group_vendor:
            return {**default, 'vat_registered': None, 'vat_number': recorded_number, 'branch_id': branch_id}
        return {**default, 'branch_id': branch_id}
    franchise = franchise_record(db, fid)
    return {'branch_id': 0, 'vat_registered': None, 'vat_number': franchise.get('vat_number') if franchise else None, 'vat_rate': 15, 'receipt_percentage': None}


@router.get('/settings')
def get_settings(franchise_user_id: int | None = None, branch_id: int = 0, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = import_scope(db, current_user, franchise_user_id)
    people = import_staff(db, fid)
    return {'franchise_user_id': fid, 'branches': branches(db, fid), 'franchise': dict(franchise_record(db, fid)), 'settings': receipt_settings(db, fid, branch_id),
            'employees': [{**p, 'commission_options': option_map(db, fid, p['user_id'])} for p in people], 'categories': COMMISSION_LABELS}


@router.put('/settings')
def save_settings(payload: SettingsIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = _staff_franchise_id(db, current_user, payload.franchise_user_id)
    if payload.branch_id and payload.branch_id not in {b['id'] for b in branches(db, fid)}:
        raise HTTPException(403, 'Branch is outside this holder group.')
    old = receipt_settings(db, fid, payload.branch_id)
    db.execute(text('''INSERT INTO receipt_commission_settings(franchise_user_id,branch_id,vat_registered,vat_number,vat_rate,receipt_percentage,updated_by_user_id)
        VALUES(:fid,:branch,:registered,:number,:vat,:rate,:actor) ON CONFLICT(franchise_user_id,branch_id)
        DO UPDATE SET vat_registered=EXCLUDED.vat_registered,vat_number=EXCLUDED.vat_number,vat_rate=EXCLUDED.vat_rate,
        receipt_percentage=EXCLUDED.receipt_percentage,updated_by_user_id=EXCLUDED.updated_by_user_id,updated_at=NOW()'''),
        {'fid': fid, 'branch': payload.branch_id, 'registered': payload.vat_registered, 'number': payload.vat_number.strip() if payload.vat_registered else None,
         'vat': payload.vat_rate, 'rate': payload.receipt_percentage, 'actor': current_user.id})
    write_audit_log(db, actor_user_id=current_user.id, franchise_user_id=fid, action='receipt_settings_updated', entity_type='receipt_commission_settings', entity_id=fid, old_values=old, new_values=payload.model_dump(mode='json'))
    db.commit()
    return {'saved': True}


@router.get('/options/{employee_user_id}')
def get_options(employee_user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    person = _participant(db, current_user, employee_user_id)
    return {'categories': COMMISSION_LABELS, 'options': option_map(db, person['franchise_user_id'], employee_user_id), 'assignment': assignment(db, employee_user_id), 'branches': branches(db, person['franchise_user_id'])}


@router.put('/options')
def save_options(payload: OptionIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = _staff_franchise_id(db, current_user, payload.franchise_user_id)
    person = _participant(db, current_user, payload.employee_user_id, write=True)
    if person['franchise_user_id'] != fid:
        raise HTTPException(403, 'Employee is outside the selected franchise.')
    old = option_map(db, fid, payload.employee_user_id)
    set_enabled_types(db, fid, payload.employee_user_id, payload.enabled_types, current_user.id)
    db.execute(text("UPDATE employee_commission_options SET rate=:rate WHERE franchise_user_id=:fid AND employee_user_id=:uid AND commission_type='invoice_commission'"), {'fid': fid, 'uid': payload.employee_user_id, 'rate': payload.receipt_percentage})
    write_audit_log(db, actor_user_id=current_user.id, franchise_user_id=fid, action='employee_commissions_updated', entity_type='employee_commission_options', entity_id=payload.employee_user_id, old_values=old, new_values=payload.model_dump(mode='json'))
    db.commit()
    return {'saved': True}


def save_document(db, fid, kind, record, staff, actor):
    require_branch(db, fid, record['branch'])
    bk, mf = branch_key(record['branch']), mf_key(record['reference'])
    if not mf:
        raise HTTPException(400, 'MF number is missing.')
    key = record['receipt_number'].strip().casefold() if kind == 'receipt' else mf
    old = db.execute(text('''SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND kind=:kind AND branch_key=:branch
        AND (document_key=:key OR (:kind='mortuary' AND mf_key=:mf)) LIMIT 1'''), {'fid': fid, 'kind': kind, 'branch': bk, 'key': key, 'mf': mf}).mappings().first()
    if old:
        data = json.loads(old['source_data'])
        if old['mf_key'] != mf or (kind == 'receipt' and any(data.get(k) != record.get(k) for k in ('gross_received', 'service_date', 'id_number'))):
            raise HTTPException(409, 'This receipt number was already imported with different details. It cannot be paid again.')
        doc_id = old['id']
    else:
        doc_id = db.execute(text('''INSERT INTO commission_documents(franchise_user_id,kind,branch_key,mf_key,document_key,source_data,source_hash,created_by_user_id)
            VALUES(:fid,:kind,:branch,:mf,:key,:source,:hash,:actor) RETURNING id'''),
            {'fid': fid, 'kind': kind, 'branch': bk, 'mf': mf, 'key': key, 'source': json.dumps(record), 'hash': record['source_hash'], 'actor': actor}).scalar_one()
    for uid, role in staff:
        # A repeated upload may add an eligible recipient, never another award for
        # the same recipient. Existing final awards retain their recorded role.
        db.execute(text('''INSERT INTO commission_document_staff(document_id,employee_user_id,removal_role)
            VALUES(:doc,:uid,:role) ON CONFLICT(document_id,employee_user_id) DO NOTHING'''), {'doc': doc_id, 'uid': uid, 'role': role})
    return doc_id, bool(old)


@router.post('/preview')
def preview(franchise_user_id: int | None = None, files: list[UploadFile] = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = import_scope(db, current_user, franchise_user_id)
    if not 1 <= len(files) <= 30:
        raise HTTPException(400, 'Upload 1–30 receipt PDFs per batch.')
    records, errors, size = [], [], 0
    for upload in files:
        name = PurePath((upload.filename or 'receipt.pdf').replace('\\', '/')).name[:255]
        content = upload.file.read(10 * 1024 * 1024 + 1); size += len(content)
        if len(content) > 10 * 1024 * 1024 or size > 50 * 1024 * 1024:
            raise HTTPException(400, 'Maximum 10 MB per PDF and 50 MB per batch.')
        try:
            parsed, failures = parse_receipt_pdf(content)
        except Exception:
            errors.append({'filename': name, 'error': 'Cannot read this receipt PDF.'}); continue
        for record in parsed:
            try:
                require_branch(db, fid, record['branch'])
            except HTTPException as exc:
                errors.append({'filename': name, 'page': record['page'], 'error': exc.detail}); continue
            record.update(filename=name, source_hash=sha256(content).hexdigest()); records.append(record)
        errors.extend(dict(e, filename=name) for e in failures)
        if len(records) + len(errors) > 100:
            raise HTTPException(400, 'Import up to 100 pages per batch.')
    return {'records': records, 'errors': errors, 'preview_token': signer().dumps({'kind': 'receipts', 'user_id': current_user.id, 'franchise_user_id': fid, 'records': records})}


@router.post('/stage')
def stage(payload: StageIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.confirmed_franchise:
        raise HTTPException(400, 'Confirm the franchise and employee selections.')
    try:
        source = signer().loads(payload.preview_token, max_age=3600)
        if source.get('kind') != 'receipts' or source.get('user_id') != current_user.id:
            raise BadSignature('Wrong preview')
    except BadSignature:
        raise HTTPException(400, 'Receipt preview expired or invalid. Upload again.')
    fid = import_scope(db, current_user, source['franchise_user_id'])
    records = source['records']
    if {a.record for a in payload.allocations} != set(range(len(records))) or len(payload.allocations) != len(records):
        raise HTTPException(400, 'Check the employee selection for each receipt.')
    try:
        db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15015, 'fid': fid})
        ids, duplicates = [], 0
        for allocation in payload.allocations:
            staff = []
            for uid in set(allocation.employee_user_ids):
                person = import_participant(db, current_user, uid, fid)
                if person['franchise_user_id'] != fid or not enabled(db, fid, uid, 'invoice_commission'):
                    raise HTTPException(403, 'Select only active franchise employees enabled for MF File Receipts.')
                staff.append((uid, None))
            doc_id, duplicate = save_document(db, fid, 'receipt', records[allocation.record], staff, current_user.id)
            ids.append(doc_id); duplicates += duplicate
        write_audit_log(db, actor_user_id=current_user.id, franchise_user_id=fid, action='mf_receipts_staged', entity_type='commission_documents', new_values={'document_ids': ids})
        db.commit()
        return {'document_ids': ids, 'saved': len(ids) - duplicates, 'duplicates': duplicates}
    except Exception:
        db.rollback(); raise


@router.get('/documents')
def documents(franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = import_scope(db, current_user, franchise_user_id)
    rows = db.execute(text('SELECT id,kind,source_data,created_at FROM commission_documents WHERE franchise_user_id=:fid ORDER BY id DESC LIMIT 100'), {'fid': fid}).mappings().all()
    return [{'id': r['id'], 'kind': r['kind'], 'record': json.loads(r['source_data']), 'created_at': r['created_at']} for r in rows]


def calculate_plan(db, fid, ids, user):
    from sqlalchemy import bindparam
    selected = db.execute(text('SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND id IN :ids').bindparams(bindparam('ids', expanding=True)), {'fid': fid, 'ids': list(set(ids))}).mappings().all()
    if len(selected) != len(set(ids)):
        raise HTTPException(403, 'Document is outside this franchise.')
    cases = {(d['branch_key'], d['mf_key']) for d in selected}
    policies = policy_map(db, fid)
    result = []
    for bk, mf in sorted(cases):
        matching_branches = [b for b in branches(db, fid) if branch_key(b['name']) == bk]
        if len(matching_branches) != 1:
            result.append({'mf': mf, 'branch': bk, 'state': 'blocked', 'reason': 'Document branch is no longer active in this holder group'})
            continue
        matched_branch = matching_branches[0]
        settings = receipt_settings(db, fid, matched_branch['id'])
        docs = db.execute(text('SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND branch_key=:branch AND mf_key=:mf ORDER BY id'), {'fid': fid, 'branch': bk, 'mf': mf}).mappings().all()
        books = [d for d in docs if d['kind'] == 'mortuary' and (d['branch_key'], d['mf_key']) == (bk, mf)]
        receipts = [d for d in docs if d['kind'] == 'receipt' and (d['branch_key'], d['mf_key']) == (bk, mf)]
        if not books or not receipts:
            result.append({'mf': mf, 'branch': bk, 'state': 'blocked', 'reason': 'Matching Mortuary Book missing' if not books else 'Matching MF File Receipt missing'})
            continue
        book = books[0]; book_data = json.loads(book['source_data'])
        receipts.sort(key=lambda d: bool(book_data.get('id_number') and json.loads(d['source_data']).get('id_number') != book_data['id_number']))
        for doc in [book, *receipts]:
            data = json.loads(doc['source_data'])
            people = db.execute(text('SELECT * FROM commission_document_staff WHERE document_id=:id ORDER BY employee_user_id'), {'id': doc['id']}).mappings().all()
            category = 'removals' if doc['kind'] == 'mortuary' else 'invoice_commission'
            matching_receipt = receipts[0] if category == 'removals' else doc
            receipt = json.loads(matching_receipt['source_data'])
            identity_error = bool(book_data.get('id_number') and receipt.get('id_number') and book_data['id_number'] != receipt['id_number'])
            for staff in people:
                uid = staff['employee_user_id']
                line = {'mf': mf, 'branch': data['branch'], 'employee_user_id': uid, 'category': category,
                        'mortuary_document_id': book['id'], 'receipt_document_id': matching_receipt['id'],
                        'service_date': data['service_date'], 'deceased': receipt.get('deceased') or book_data.get('deceased'),
                        'id_number': receipt.get('id_number') or book_data.get('id_number'),
                        'receipt_number': receipt.get('receipt_number'), 'reference': book_data['reference'],
                        'gross_received': receipt.get('gross_received'), 'state': 'ready', 'reason': '', 'amount': None}
                try:
                    person = import_participant(db, user, uid, fid)
                    if person['franchise_user_id'] != fid:
                        raise HTTPException(403, 'Outside franchise')
                    line['employee_name'] = person['full_name']
                    line['employee_branch_id'] = person.get('branch_id')
                    line['employee_branch_name'] = person.get('branch_name')
                except HTTPException:
                    line.update(state='blocked', reason='Employee inactive or outside franchise', employee_name=f'Staff #{uid}')
                options = option_map(db, fid, uid)
                existing = db.execute(text("SELECT id FROM commission_entries WHERE employee_user_id=:uid AND commission_type=:type AND " + ('mortuary_document_id=:doc' if category == 'removals' else 'receipt_document_id=:doc')), {'uid': uid, 'type': category, 'doc': doc['id']}).scalar()
                if existing:
                    line.update(state='already_recorded', reason='Commission already recorded')
                elif not options.get(category, {}).get('enabled'):
                    line.update(state='blocked', reason='Commission category disabled for this employee')
                elif identity_error:
                    line.update(state='blocked', reason='MF matches but deceased ID numbers differ')
                if not existing:
                    reference = book_data['reference'] if category == 'removals' else f"{book_data['reference']} / Receipt {receipt['receipt_number']}"
                    try:
                        _assert_not_duplicate(db, fid, uid, EntryIn(commission_type=category, service_date=data['service_date'], reference=reference[:255], branch_name=data['branch']))
                    except HTTPException as exc:
                        if exc.status_code != 409:
                            raise
                        line.update(state='already_recorded', reason='Matching commission already recorded manually')
                if category == 'removals':
                    policy = effective_policy(policies, uid)
                    fee = price_removal(book_data, staff['removal_role'] or 'driver', policy, effective_policy(policies, 0).get('extra_holidays', []))
                    line.update(amount=fee['amount'], rate=fee['amount'], band=fee['band'], role=staff['removal_role'], notes=book_data)
                    if line['amount'] is None and line['state'] == 'ready':
                        line.update(state='blocked', reason='Removal fee not configured')
                else:
                    rate = options.get(category, {}).get('rate')
                    if rate is None:
                        rate = settings.get('receipt_percentage')
                    line.update(rate=str(rate) if rate is not None else None, vat_registered=settings['vat_registered'], vat_rate=str(settings['vat_rate']))
                    if settings['vat_registered'] is None:
                        if line['state'] == 'ready': line.update(state='blocked', reason='Confirm franchise VAT registration status')
                    else:
                        base = receipt_base(receipt['gross_received'], settings['vat_registered'], settings['vat_rate'])
                        line.update(base_amount=str(base), vat_number=settings.get('vat_number'), amount=str(money(base * Decimal(str(rate)) / 100)) if rate is not None else None)
                    if rate is None and line['state'] == 'ready':
                        line.update(state='blocked', reason='Receipt commission percentage not configured')
                result.append(line)
    return result


def plan_digest(plan):
    return sha256(json.dumps(plan, sort_keys=True, default=str).encode()).hexdigest()


@router.post('/calculate')
def calculate(payload: CalculateIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = import_scope(db, current_user, payload.franchise_user_id)
    plan = calculate_plan(db, fid, payload.document_ids, current_user)
    return {'items': plan, 'total': str(sum((Decimal(r['amount']) for r in plan if r['state'] == 'ready'), Decimal(0))),
            'quote_token': signer().dumps({'kind': 'paired_commission_quote', 'user_id': current_user.id, 'fid': fid, 'ids': sorted(set(payload.document_ids)), 'digest': plan_digest(plan)})}


@router.post('/settle')
def settle(payload: CalculateIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = import_scope(db, current_user, payload.franchise_user_id)
    try:
        saved = signer().loads(payload.quote_token or '', max_age=3600)
        if saved.get('kind') != 'paired_commission_quote' or saved.get('user_id') != current_user.id or saved.get('fid') != fid or saved.get('ids') != sorted(set(payload.document_ids)):
            raise BadSignature('Wrong quote')
    except BadSignature:
        raise HTTPException(400, 'Calculate and review matched commissions first.')
    try:
        db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15015, 'fid': fid})
        plan = calculate_plan(db, fid, payload.document_ids, current_user)
        if saved['digest'] != plan_digest(plan):
            raise HTTPException(409, 'Documents, employee eligibility or rates changed. Calculate again.')
        ids = []
        for item in plan:
            if item['state'] != 'ready':
                continue
            reference = item['reference'] if item['category'] == 'removals' else f"{item['reference']} / Receipt {item['receipt_number']}"
            notes = '\n'.join(f'{k}: {v}' for k, v in item.items() if k not in {'notes', 'state', 'reason'} and v is not None)
            if item.get('notes'):
                notes += '\n' + '\n'.join(f'{k}: {item["notes"].get(k, "-")}' for k in ('deceased', 'id_number', 'collected_at', 'driver_in', 'date_in', 'time_in'))
            entry = db.execute(text('''INSERT INTO commission_entries(franchise_user_id,employee_user_id,commission_type,service_date,reference,quantity,
                applied_rate,calculated_amount,invoice_value_before_tax,notes,branch_name,created_by_user_id,status,submitted_at,reviewed_at,
                reviewed_by_user_id,last_edited_by_user_id,mortuary_document_id,receipt_document_id,source_metadata)
                VALUES(:fid,:uid,:type,:day,:ref,1,:rate,:amount,:base,:notes,:branch,:actor,'approved',NOW(),NOW(),:actor,:actor,:book,:receipt,:metadata) RETURNING *'''),
                {'fid': fid, 'uid': item['employee_user_id'], 'type': item['category'], 'day': date.fromisoformat(item['service_date']), 'ref': reference[:255],
                 'rate': Decimal(item['rate']), 'amount': Decimal(item['amount']), 'base': Decimal(item['base_amount']) if item.get('base_amount') is not None else None,
                 'notes': notes, 'branch': item['branch'], 'actor': current_user.id, 'book': item['mortuary_document_id'], 'receipt': item['receipt_document_id'], 'metadata': json.dumps(item, default=str)}).mappings().first()
            _audit(db, entry['id'], 'matched_documents_commission', current_user.id, new=dict(entry))
            _notify(db, item['employee_user_id'], 'Matched commission added', f"{COMMISSION_LABELS[item['category']]} · {reference}", entry['id'], 'success')
            ids.append(entry['id'])
        db.commit()
        return {'created': len(ids), 'entry_ids': ids, 'blocked': sum(r['state'] == 'blocked' for r in plan)}
    except IntegrityError:
        db.rollback(); raise HTTPException(409, 'An award was saved concurrently. Calculate again.')
    except Exception:
        db.rollback(); raise


@router.get('/access')
def access(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        fid = import_scope(db, current_user)
        return {'can_import': True, 'franchise_user_id': fid}
    except HTTPException:
        return {'can_import': False}


@router.get('/branches')
def branch_list(franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return branches(db, import_scope(db, current_user, franchise_user_id))


@router.get('/report.pdf')
def report(month: str, franchise_user_id: int | None = None, branch_id: int | None = None,
           employee_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from calendar import monthrange
    from datetime import datetime
    from io import BytesIO
    from xml.sax.saxutils import escape
    from fastapi.responses import StreamingResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from app.api.commission import _rows
    fid = _staff_franchise_id(db, current_user, franchise_user_id)
    if branch_id and branch_id not in {b['id'] for b in branches(db, fid, False)}:
        raise HTTPException(403, 'Branch is outside this holder group.')
    try:
        first = datetime.strptime(month, '%Y-%m').date().replace(day=1)
        last = first.replace(day=monthrange(first.year, first.month)[1])
    except ValueError:
        raise HTTPException(400, 'Select a valid report month.')
    rows = _rows(db, current_user, employee_user_id=employee_user_id, from_date=first, to_date=last, status='approved', franchise_user_id=fid)
    grouped = {}
    for row in rows:
        metadata = json.loads(row.get('source_metadata') or '{}')
        home = assignment(db, row['employee_user_id']) or {}
        bid = metadata.get('employee_branch_id') or home.get('branch_id')
        if branch_id and bid != branch_id:
            continue
        branch_name = metadata.get('employee_branch_name') or home.get('branch_name') or 'Unassigned branch'
        grouped.setdefault(branch_name, {}).setdefault((row['employee_user_id'], row['employee_name']), {}).setdefault(row['commission_type'], []).append((row, metadata))
    stream = BytesIO(); styles = getSampleStyleSheet()
    styles['BodyText'].fontSize = 8; styles['BodyText'].leading = 11
    def para(value):
        return Paragraph(escape(str(value if value is not None else '—')).replace('\n', '<br/>'), styles['BodyText'])
    story = [Paragraph('Monthly employee commission statement', styles['Title']), Paragraph(escape(month), styles['Heading2']), para('Approved commissions only. Unmatched, disabled and waiting items do not earn commission.'), Spacer(1, 5 * mm)]
    grand = Decimal(0)
    for branch_name, people in sorted(grouped.items()):
        story.append(Paragraph(escape(branch_name), styles['Heading1'])); branch_total = Decimal(0)
        for (_, name), categories in sorted(people.items(), key=lambda item: item[0][1]):
            story.append(Paragraph(escape(name), styles['Heading2'])); employee_total = Decimal(0)
            for category, entries in categories.items():
                story.append(Paragraph(escape(COMMISSION_LABELS.get(category, category)), styles['Heading3']))
                data = [[para(x) for x in ('Date', 'MF / Receipt / Document branch', 'Deceased / ID', 'Amount received', 'Commissionable amount', 'Fee / Rate', 'Commission')]]
                subtotal = Decimal(0)
                for row, meta in entries:
                    amount = money(row['calculated_amount']); subtotal += amount
                    values = [row['service_date'], f"{row['reference']}\n{row.get('branch_name') or ''}", f"{meta.get('deceased') or '—'}\n{meta.get('id_number') or '—'}",
                              f"R {money(meta['gross_received']):,.2f}" if meta.get('gross_received') else '—',
                              f"R {money(row['invoice_value_before_tax']):,.2f}" if row.get('invoice_value_before_tax') is not None else '—',
                              f"{row['applied_rate']}%" if category == 'invoice_commission' else f"{row['applied_rate']}x" if category == 'overtime' else f"R {money(row['applied_rate']):,.2f}", f'R {amount:,.2f}']
                    data.append([para(v) for v in values])
                table = Table(data, colWidths=[20*mm,45*mm,65*mm,32*mm,32*mm,25*mm,32*mm], repeatRows=1, hAlign='LEFT')
                table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eee8f5')),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#ddd5e8')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
                story.extend([table, para(f'{COMMISSION_LABELS.get(category, category)} subtotal: R {subtotal:,.2f}'), Spacer(1,4*mm)])
                employee_total += subtotal
            story.append(Paragraph(f'Employee total: R {employee_total:,.2f}', styles['Heading3'])); branch_total += employee_total
        story.append(Paragraph(f'Branch total: R {branch_total:,.2f}', styles['Heading2'])); grand += branch_total
    if not grouped:
        story.append(para('No approved commissions for the selected month and scope.'))
    story.append(Paragraph(f'Grand total: R {grand:,.2f}', styles['Heading1']))
    SimpleDocTemplate(stream, pagesize=landscape(A4), leftMargin=14*mm, rightMargin=14*mm, topMargin=14*mm, bottomMargin=14*mm).build(story)
    stream.seek(0)
    return StreamingResponse(stream, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="commissions-{month}.pdf"'})
