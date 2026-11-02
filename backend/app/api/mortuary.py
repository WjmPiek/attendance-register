"""Franchise-controlled, previewed and atomic Mortuary Book commissions."""
from copy import deepcopy
from datetime import date, time
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import PurePath
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.commission import _participant, _audit, _notify, _assert_not_duplicate, EntryIn, employees
from app.api.deps import get_current_user
from app.api.franchise_staff import _staff_franchise_id
from app.core.config import settings
from app.db.session import get_db
from app.models.core import User
from app.services.mortuary import DEFAULT_WEEK, RATE_KEYS, match_employee, normalise, parse_pdf, price_removal

from app.services.attendance_branches import import_scope, import_staff, import_participant

router = APIRouter()


class Window(BaseModel):
    start: str = Field(pattern=r'^\d{2}:\d{2}$')
    end: str = Field(pattern=r'^\d{2}:\d{2}$')

    @model_validator(mode='after')
    def valid_window(self):
        if time.fromisoformat(self.start) >= time.fromisoformat(self.end):
            raise ValueError('Business hours must start before they end. Use a closed day for no business hours.')
        return self


class Rates(BaseModel):
    driver_in: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    driver_out: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    assistant_in: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    assistant_out: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    driver_sunday_holiday: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    assistant_sunday_holiday: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    driver_other_branch: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    assistant_other_branch: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)

    driver_grave_service: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    driver_full_funeral_service: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    driver_cremation_service: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    driver_church_service: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    driver_joinings: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    driver_overtime: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    driver_invoice_commission: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=4)
    assistant_grave_service: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    assistant_full_funeral_service: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    assistant_cremation_service: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    assistant_church_service: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    assistant_joinings: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    assistant_overtime: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    assistant_invoice_commission: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=4)


class Policy(BaseModel):
    week: list[Window | None] = Field(min_length=6, max_length=6)
    rates: Rates
    extra_holidays: list[date] = Field(default_factory=list, max_length=100)


class SavePolicy(Policy):
    franchise_user_id: int | None = None
    employee_user_id: int = Field(default=0, ge=0)


class Allocation(BaseModel):
    record: int = Field(ge=0)
    name_index: int = Field(ge=0)
    employee_user_id: int = Field(gt=0)
    role: Literal['driver', 'assistant']


class ImportIn(BaseModel):
    preview_token: str = Field(max_length=2000000)
    allocations: list[Allocation] = Field(min_length=1, max_length=500)
    confirmed_franchise: bool = False
    quote_token: str | None = None


def signer():
    return URLSafeTimedSerializer(settings.JWT_SECRET_KEY, salt='mortuary-book-preview-v1')


def read_preview(token, uid):
    try:
        data = signer().loads(token, max_age=3600)
        if data['user_id'] != uid or data.get('kind') != 'preview' or not isinstance(data.get('records'), list):
            raise ValueError('Wrong user')
        return data
    except (BadSignature, KeyError, ValueError):
        raise HTTPException(400, 'Import preview expired or invalid. Upload the books again.')


def policy_map(db, fid):
    return {int(r['employee_user_id']): json.loads(r['policy']) for r in db.execute(text(
        'SELECT employee_user_id, policy FROM mortuary_policies WHERE franchise_user_id=:fid'
    ), {'fid': fid}).mappings().all()}


def effective_policy(policies, uid):
    default = policies.get(0, {'week': DEFAULT_WEEK, 'rates': {k: None for k in RATE_KEYS}, 'extra_holidays': []})
    own = policies.get(uid)
    result = deepcopy(default)
    if own:
        result['week'] = deepcopy(own['week'])
        result['rates'].update({k: v for k, v in own['rates'].items() if v is not None})
    return result


@router.get('/settings')
def get_settings(franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = import_scope(db, current_user, franchise_user_id)
    people = import_staff(db, fid)
    policies = policy_map(db, fid)
    return {'employees': people, 'default': effective_policy(policies, 0), 'overrides': policies,
            'franchise_user_id': fid}


@router.put('/settings')
def save_settings(payload: SavePolicy, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = _staff_franchise_id(db, current_user, payload.franchise_user_id)
    if payload.employee_user_id:
        participant = _participant(db, current_user, payload.employee_user_id, write=True)
        if participant['franchise_user_id'] != fid:
            raise HTTPException(403, 'Staff member is outside this franchise')
        if payload.extra_holidays:
            raise HTTPException(400, 'Set additional public holidays on franchise defaults.')
    policy = payload.model_dump(mode='json', exclude={'franchise_user_id', 'employee_user_id'})
    old = db.execute(text('SELECT policy FROM mortuary_policies WHERE franchise_user_id=:fid AND employee_user_id=:uid'),
                     {'fid': fid, 'uid': payload.employee_user_id}).scalar()
    db.execute(text('''INSERT INTO mortuary_policies(franchise_user_id,employee_user_id,policy,updated_by_user_id)
        VALUES(:fid,:uid,:policy,:actor) ON CONFLICT(franchise_user_id,employee_user_id)
        DO UPDATE SET policy=EXCLUDED.policy,updated_by_user_id=EXCLUDED.updated_by_user_id,updated_at=NOW()'''),
        {'fid': fid, 'uid': payload.employee_user_id, 'policy': json.dumps(policy), 'actor': current_user.id})
    # Use the existing system audit trail for policy changes.
    from app.services.audit import write_audit_log
    write_audit_log(db, actor_user_id=current_user.id, action='mortuary_policy_updated',
                    entity_type='mortuary_policy', entity_id=payload.employee_user_id,
                    franchise_user_id=fid, old_values={'policy': old}, new_values=policy)
    db.commit()
    return {'saved': True}


@router.post('/preview')
def preview(franchise_user_id: int | None = None, external_branch_id: int | None = None, files: list[UploadFile] = File(...),
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = import_scope(db, current_user, franchise_user_id)
    if not 1 <= len(files) <= 30:
        raise HTTPException(400, 'Upload between 1 and 30 PDF files at a time.')
    records, errors, total_bytes = [], [], 0
    for upload in files:
        filename = PurePath((upload.filename or 'book.pdf').replace('\\', '/')).name[:255]
        data = upload.file.read(10 * 1024 * 1024 + 1)
        total_bytes += len(data)
        if len(data) > 10 * 1024 * 1024 or total_bytes > 50 * 1024 * 1024:
            raise HTTPException(400, 'Maximum 10 MB per PDF and 50 MB per batch.')
        try:
            parsed, failures = parse_pdf(data)
        except Exception:
            errors.append({'filename': filename, 'error': 'Cannot read this PDF. Use the original unprotected Mortuary Book PDF.'})
            continue
        for item in parsed:
            if external_branch_id:
                from app.api.receipt_commissions import require_branch
                item['earning_branch_id'] = require_branch(db, fid, item['branch'], external_branch_id)
                item['external_branch_id'] = external_branch_id
            item.update(filename=filename, source_hash=sha256(data).hexdigest())
        records.extend(parsed)
        errors.extend(dict(f, filename=filename) for f in failures)
        if len(records) + len(errors) > 100:
            raise HTTPException(400, 'Import up to 100 pages per batch.')
    people = import_staff(db, fid)
    suggestions = []
    for i, record in enumerate(records):
        for n, name in enumerate(record['names']):
            # Driver field is authoritative when it identifies one of Driver In.
            role = 'driver' if normalise(name) == normalise(record['driver']) or len(record['names']) == 1 else 'assistant'
            suggestions.append({'record': i, 'name_index': n, 'employee_user_id': match_employee(name, people), 'role': role})
    token = signer().dumps({'kind': 'preview', 'user_id': current_user.id, 'franchise_user_id': fid, 'records': records})
    return {'records': records, 'errors': errors, 'allocations': suggestions, 'preview_token': token}


def evaluate_import(db, user, payload):
    source = read_preview(payload.preview_token, user.id)
    fid = import_scope(db, user, source['franchise_user_id'])
    records = source['records']
    expected = {(i, n) for i, record in enumerate(records) for n in range(len(record['names']))}
    supplied = {(a.record, a.name_index) for a in payload.allocations}
    if supplied != expected or len(supplied) != len(payload.allocations):
        raise HTTPException(400, 'Allocate each Driver In name exactly once before importing.')
    policies = policy_map(db, fid)
    results, seen, per_record = [], set(), set()
    for a in payload.allocations:
        if (a.record, a.employee_user_id) in per_record:
            raise HTTPException(400, 'Two Driver In names on the same record must be allocated to different employees.')
        per_record.add((a.record, a.employee_user_id))
        record = records[a.record]
        participant = import_participant(db, user, a.employee_user_id, fid)
        if participant['franchise_user_id'] != fid:
            raise HTTPException(403, 'Staff member is outside this franchise')
        branch_key, reference_key = normalise(record['branch']), record['reference'].strip().casefold()
        identity = (a.employee_user_id, branch_key, reference_key)
        if not branch_key or not reference_key:
            raise HTTPException(400, 'Branch and MF Number are required.')
        policy = effective_policy(policies, a.employee_user_id)
        from app.services.receipt_commissions import branch_key as earning_branch_key
        from app.services.attendance_branches import branches
        other_branch = earning_branch_key(record['branch']) not in {earning_branch_key(b['name']) for b in branches(db, fid)}
        try:
            quote = price_removal(record, a.role, policy, effective_policy(policies, 0).get('extra_holidays', []), other_branch=False, staff_hours=participant)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, f"Check saved working hours for {participant['full_name']} in Edit Staff: {exc}")
        duplicate = identity in seen or bool(db.execute(text('''SELECT 1 FROM mortuary_import_allocations
            WHERE franchise_user_id=:fid AND employee_user_id=:uid AND branch_key=:branch AND reference_key=:ref'''),
            {'fid': fid, 'uid': a.employee_user_id, 'branch': branch_key, 'ref': reference_key}).scalar())
        # Two source names cannot be allocated to the same employee for one removal.
        seen.add(identity)
        if not duplicate:
            try:
                _assert_not_duplicate(db, fid, a.employee_user_id, EntryIn(commission_type='removals', service_date=record['service_date'], reference=record['reference'], branch_name=record['branch']))
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
                duplicate = True
        results.append({**a.model_dump(), **quote, 'employee_name': participant['full_name'],
                        'duplicate': duplicate, 'record_data': record, 'branch_key': branch_key,
                        'reference_key': reference_key, 'franchise_user_id': fid})
    return results


@router.post('/quote')
def quote(payload: ImportIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    results = evaluate_import(db, current_user, payload)
    return {'items': results, 'total': str(sum((Decimal(r['amount']) for r in results if not r['duplicate'] and r['amount'] is not None), Decimal(0))),
            'quote_token': signer().dumps({'kind': 'quote', 'user_id': current_user.id, 'digest': quote_digest(results)})}


def quote_digest(rows):
    return sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


@router.post('/import')
def import_books(payload: ImportIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.confirmed_franchise:
        raise HTTPException(400, 'Confirm that every book belongs to the selected franchise.')
    try:
        # Serialise imports and normal commission writes for this franchise.
        source = read_preview(payload.preview_token, current_user.id)
        fid = import_scope(db, current_user, source['franchise_user_id'])
        db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15015, 'fid': fid})
        rows = evaluate_import(db, current_user, payload)
        try:
            saved_quote = signer().loads(payload.quote_token or '', max_age=3600)
        except BadSignature:
            raise HTTPException(400, 'Calculate and review the commissions before importing.')
        if saved_quote.get('kind') != 'quote' or saved_quote.get('user_id') != current_user.id or saved_quote.get('digest') != quote_digest(rows):
            raise HTTPException(409, 'Rates, assignments or duplicate status changed. Calculate and review the commissions again.')
        from app.api.receipt_commissions import save_document
        ids, duplicates = [], 0
        for index, record in enumerate(source['records']):
            selected = [r for r in rows if r['record'] == index]
            staff = [(r['employee_user_id'], r['role']) for r in selected]
            doc_id, duplicate = save_document(db, fid, 'mortuary', record, staff, current_user.id)
            ids.append(doc_id); duplicates += duplicate
        from app.services.audit import write_audit_log
        write_audit_log(db, actor_user_id=current_user.id, franchise_user_id=fid, action='mortuary_books_staged', entity_type='commission_documents', new_values={'document_ids': ids})
        db.commit()
        return {'created': 0, 'saved_books': len(ids) - duplicates, 'skipped_duplicates': duplicates, 'document_ids': ids, 'totals': {}, 'message': 'Books saved. Commission is blocked until matching MF File Receipts are present. Review matched commissions on the MF File Receipt tab.'}
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An import changed at the same time. Refresh the preview before importing again.')
    except Exception:
        db.rollback()
        raise
