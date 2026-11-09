"""Stage receipt evidence, then approve only paired, opted-in commissions."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import PurePath

from fastapi import BackgroundTasks, APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from itsdangerous import BadSignature
from pydantic import BaseModel, Field, model_validator
from typing import Literal
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
    parse_receipt_pdf, receipt_base, set_enabled_types, branch_options, enabled_for_branch, save_branch_options, CommissionBranchOptions,
)
from app.services.audit import write_audit_log
from app.services.mortuary import normalise
from app.services.invoice_proof import parse_invoice_pdf
from app.services.pdf_records import imported_page_count

from app.services.attendance_branches import import_scope, import_staff, import_participant, branches, assignment

router = APIRouter()


class OptionIn(BaseModel):
    employee_user_id: int
    franchise_user_id: int | None = None
    branch_id: int | None = Field(default=None, gt=0)
    enabled_types: list[str] = Field(default_factory=list, max_length=8)
    commission_branches: dict[int, CommissionBranchOptions] | None = None
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
    employee_roles: dict[int, Literal["driver", "assistant"]] = Field(default_factory=dict)
    record: int = Field(ge=0)
    employee_user_ids: list[int] = Field(max_length=100)


class StageIn(BaseModel):
    preview_token: str = Field(max_length=2000000)
    allocations: list[ReceiptAllocation] = Field(default_factory=list, max_length=100)
    confirmed_franchise: bool = False


class CalculateIn(BaseModel):
    franchise_user_id: int | None = None
    document_ids: list[int] = Field(min_length=1, max_length=100)
    quote_token: str | None = Field(default=None, max_length=2000000)


class ExternalBranchIn(BaseModel):
    franchise_user_id: int | None = None
    name: str = Field(min_length=2, max_length=255)
    vat_number: str | None = Field(default=None, pattern=r'^\d{10}$')


@router.get('/external-branches')
def list_external_branches(franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.api.commission import _profile, _franchise_scope
    from app.services.external_commissions import external_branches
    roles, _, _, _, _ = _profile(db, current_user)
    fid = _franchise_scope(db, current_user, franchise_user_id)
    return {'branches': external_branches(db, fid) if fid else [], 'can_manage': bool({'FranchiseUser', 'SuperUser'} & roles)}


class UploadersIn(BaseModel):
    franchise_user_id: int | None = None
    employee_user_ids: list[int] = Field(max_length=1000)


@router.get('/uploaders')
def get_uploaders(franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.api.commission import _profile
    roles, _, _, _, _ = _profile(db, current_user)
    if not {'FranchiseUser', 'SuperUser'} & roles:
        raise HTTPException(403, 'Only the holder can manage document uploaders.')
    fid = _staff_franchise_id(db, current_user, franchise_user_id)
    return import_staff(db, fid)


@router.put('/uploaders')
def set_uploaders(payload: UploadersIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    people = get_uploaders(payload.franchise_user_id, current_user, db)
    selected = set(payload.employee_user_ids)
    if selected - {p['user_id'] for p in people}:
        raise HTTPException(403, 'Choose only active staff belonging to this holder.')
    fid = _staff_franchise_id(db, current_user, payload.franchise_user_id)
    for person in people:
        db.execute(text('UPDATE employee_branch_assignments SET can_import_commissions=:enabled WHERE franchise_user_id=:fid AND employee_user_id=:uid'), {'enabled': person['user_id'] in selected, 'fid': fid, 'uid': person['user_id']})
    write_audit_log(db, actor_user_id=current_user.id, franchise_user_id=fid, action='commission_uploaders_updated', entity_type='employee_branch_assignments', new_values={'employee_user_ids': sorted(selected)})
    db.commit()
    return {'saved': True}


@router.post('/external-branches')
def declare_external_branch(payload: ExternalBranchIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.api.commission import _profile
    from app.services.external_commissions import external_branches, outside_group
    roles, _, _, _, _ = _profile(db, current_user)
    if not {'FranchiseUser', 'SuperUser'} & roles:
        raise HTTPException(403, 'Only the franchise holder may declare an outside service branch.')
    fid = _staff_franchise_id(db, current_user, payload.franchise_user_id)
    name = payload.name.strip()
    if not branch_key(name) or not outside_group(db, fid, name):
        raise HTTPException(400, 'This is a linked branch. Use the linked branch import option.')
    db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15015, 'fid': fid})
    existing = next((b for b in external_branches(db, fid) if branch_key(b['name']) == branch_key(name)), None)
    if existing:
        return existing
    bid = db.execute(text('INSERT INTO attendance_branches(franchise_user_id,name,vat_number,is_active,main_synced) VALUES(:fid,:name,:vat,TRUE,FALSE) RETURNING id'), {'fid': fid, 'name': name, 'vat': payload.vat_number}).scalar_one()
    db.execute(text('INSERT INTO external_commission_branches(branch_id,franchise_user_id,branch_key,created_by_user_id) VALUES(:bid,:fid,:key,:actor)'), {'bid': bid, 'fid': fid, 'key': branch_key(name), 'actor': current_user.id})
    write_audit_log(db, actor_user_id=current_user.id, franchise_user_id=fid, action='external_service_branch_declared', entity_type='attendance_branches', entity_id=bid, new_values={'name': name})
    db.commit()
    return next(b for b in external_branches(db, fid) if b['id'] == bid)


def franchise_record(db, fid):
    return db.execute(text('SELECT id,franchise_name,business_name,trading_as,vat_number FROM franchise_users WHERE id=:fid AND COALESCE(is_active,TRUE)=TRUE'), {'fid': fid}).mappings().first()


def require_branch(db, fid, value, external_branch_id=None):
    franchise = franchise_record(db, fid)
    available = branches(db, fid)
    if external_branch_id:
        from app.services.external_commissions import external_branches, outside_group
        selected = next((b for b in external_branches(db, fid) if b['id'] == external_branch_id), None)
        if not selected or branch_key(selected['name']) != branch_key(value) or not outside_group(db, fid, value):
            raise HTTPException(400, 'Printed branch must match the declared outside branch and be outside the linked group.')
        return selected['id']
    aliases = {branch_key(b['name']) for b in available}
    if not available:
        aliases = {branch_key(franchise.get(k) or '') for k in ('franchise_name', 'business_name', 'trading_as')} if franchise else set()
    if sum(branch_key(b['name']) == branch_key(value) for b in available) > 1:
        raise HTTPException(400, 'Printed branch name is ambiguous within this holder group. Use distinct branch names before importing.')
    if not branch_key(value) or branch_key(value) not in aliases:
        from app.services.external_commissions import external_branches
        outside = [b for b in external_branches(db,fid) if branch_key(b['name'])==branch_key(value)]
        if len(outside)==1:
            return outside[0]['id']
        raise HTTPException(400, f'Printed franchise "{value}" does not match this franchise profile. Correct the franchise profile or use its own document.')
    return next((b['id'] for b in available if branch_key(b['name'])==branch_key(value)), None)


def check_import_branch(db,fid,record,external_branch_id=None,expected_branch_id=None):
    if external_branch_id and expected_branch_id:
        raise HTTPException(400,'Choose either a linked branch or an outside branch.')
    if expected_branch_id and expected_branch_id not in {b['id'] for b in branches(db,fid)}:
        raise HTTPException(403,'Selected branch is outside this holder group.')
    actual=require_branch(db,fid,record['branch'],external_branch_id)
    if expected_branch_id and actual!=expected_branch_id:
        selected=next(b['name'] for b in branches(db,fid) if b['id']==expected_branch_id)
        raise HTTPException(400,f'Printed branch "{record["branch"]}" does not match selected branch "{selected}". Choose automatic detection or the correct branch.')
    return actual


def suggest_receipt_allocations(db,fid,records,user):
    from app.services.external_commissions import permission_branch
    result=[]
    for index,record in enumerate(records):
        people=[];roles={}
        books=db.execute(text("SELECT id,source_data FROM commission_documents WHERE franchise_user_id=:fid AND kind='mortuary' AND branch_key=:branch AND mf_key=:mf AND deleted_at IS NULL"),{'fid':fid,'branch':branch_key(record['branch']),'mf':mf_key(record['reference'])}).mappings().all()
        if len(books)==1:
            book=json.loads(books[0]['source_data'])
            matches=normalise(book.get('deceased'))==normalise(record.get('deceased')) and bool(normalise(record.get('deceased')))
            matches=matches and not (book.get('id_number') and record.get('id_number') and book['id_number']!=record['id_number'])
            if matches:
                staff=db.execute(text('SELECT employee_user_id,removal_role FROM commission_document_staff WHERE document_id=:id'),{'id':books[0]['id']}).mappings().all()
                for person in staff:
                    uid=person['employee_user_id']
                    try:
                        import_participant(db,user,uid,fid)
                        if enabled_for_branch(db,fid,uid,'invoice_commission',permission_branch(db,fid,uid,record['earning_branch_id'])):
                            people.append(uid);roles[uid]=person['removal_role'] or 'driver'
                    except HTTPException: continue
        result.append({'record':index,'employee_user_ids':people,'employee_roles':roles})
    return result


def receipt_settings(db, fid, branch_id=0):
    row = db.execute(text('SELECT * FROM receipt_commission_settings WHERE franchise_user_id=:fid AND branch_id=:branch'), {'fid': fid, 'branch': branch_id}).mappings().first()
    default = receipt_settings(db, fid, 0) if branch_id else None
    if branch_id:
        synced = db.execute(text('SELECT vat_number,main_synced FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid'), {'id': branch_id, 'fid': fid}).mappings().first()
        if synced and synced['main_synced']:
            number = str(synced['vat_number'] or '').strip()
            result = {**default, **(dict(row) if row else {}), 'branch_id': branch_id,
                      'vat_registered': bool(number), 'vat_number': number or None, 'vat_from_main_system': True}
            if not number: result['vat_rate'] = 0
            if result.get('receipt_percentage') is None: result['receipt_percentage'] = default.get('receipt_percentage')
            return result
    if row:
        result = dict(row)
        result['vat_registered'] = bool(result['vat_registered'])
        if branch_id and result.get('receipt_percentage') is None:
            result['receipt_percentage'] = default.get('receipt_percentage')
        return result
    if branch_id:
        from app.services.external_commissions import external_branches, is_external
        branch = next((b for b in branches(db, fid) + external_branches(db, fid) if b['id'] == branch_id), None)
        if not branch:
            raise HTTPException(403, 'Branch is outside this holder group.')
        recorded_number = str(branch.get('vat_number') or '').strip()
        if is_external(db, fid, branch_id):
            return {**default, 'vat_registered': True if recorded_number else None, 'vat_number': recorded_number or None, 'branch_id': branch_id}
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
    from app.api.commission import _profile
    roles, _, _, _, _ = _profile(db, current_user)
    return {'can_approve': bool({'FranchiseUser', 'SuperUser'} & roles), 'franchise_user_id': fid, 'branches': branches(db, fid), 'franchise': dict(franchise_record(db, fid)), 'settings': receipt_settings(db, fid, branch_id),
            'employees': [{**p, 'commission_options': option_map(db, fid, p['user_id']), 'commission_branches': branch_options(db,fid,p['user_id'])} for p in people], 'categories': COMMISSION_LABELS}


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
    return {'categories': COMMISSION_LABELS, 'options': option_map(db, person['franchise_user_id'], employee_user_id), 'commission_branches': branch_options(db,person['franchise_user_id'],employee_user_id), 'assignment': assignment(db, employee_user_id), 'branches': branches(db, person['franchise_user_id'])}


@router.put('/options')
def save_options(payload: OptionIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = _staff_franchise_id(db, current_user, payload.franchise_user_id)
    person = _participant(db, current_user, payload.employee_user_id, write=True)
    if person['franchise_user_id'] != fid:
        raise HTTPException(403, 'Employee is outside the selected franchise.')
    old = option_map(db, fid, payload.employee_user_id)
    if payload.branch_id is not None and payload.commission_branches is None:
        raise HTTPException(400, 'Supply commission settings for the selected branch only.')
    if payload.commission_branches is not None:
        save_branch_options(db,fid,payload.employee_user_id,payload.commission_branches,current_user.id,branch_id=payload.branch_id)
    else:
        # Older clients may update global flags; retain only existing branch grants.
        current = branch_options(db,fid,payload.employee_user_id)
        for value in current.values():
            value['enabled_types']=[c for c in value['enabled_types'] if c in payload.enabled_types]
        home = str(assignment(db,payload.employee_user_id)['branch_id'])
        for category in payload.enabled_types:
            if not any(category in value['enabled_types'] for value in current.values()):
                current.setdefault(home,{'enabled_types':[],'receipt_percentage':None})['enabled_types'].append(category)
        save_branch_options(db,fid,payload.employee_user_id,current,current_user.id)
    if payload.branch_id is None and 'receipt_percentage' in payload.model_fields_set:
        db.execute(text("UPDATE employee_commission_options SET rate=:rate WHERE franchise_user_id=:fid AND employee_user_id=:uid AND commission_type='invoice_commission'"), {'fid': fid, 'uid': payload.employee_user_id, 'rate': payload.receipt_percentage})
    write_audit_log(db, actor_user_id=current_user.id, franchise_user_id=fid, action='employee_commissions_updated', entity_type='employee_commission_options', entity_id=payload.employee_user_id, old_values=old, new_values=payload.model_dump(mode='json'))
    db.commit()
    return {'saved': True}


def save_document(db, fid, kind, record, staff, actor):
    require_branch(db, fid, record['branch'], record.get('external_branch_id'))
    bk, mf = branch_key(record['branch']), mf_key(record['reference'])
    if not mf:
        raise HTTPException(400, 'MF number is missing.')
    key = record['receipt_number'].strip().casefold() if kind == 'receipt' else normalise(record['invoice_number']) if kind == 'invoice' else mf
    old = db.execute(text('''SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND kind=:kind AND branch_key=:branch
        AND deleted_at IS NULL AND (document_key=:key OR (:kind IN ('mortuary','invoice') AND mf_key=:mf)) LIMIT 1'''), {'fid': fid, 'kind': kind, 'branch': bk, 'key': key, 'mf': mf}).mappings().first()
    if old:
        data = json.loads(old['source_data'])
        immutable = ('gross_received', 'service_date', 'id_number', 'deceased', 'invoice_number') if kind == 'receipt' else ('invoice_number', 'invoice_total', 'deceased', 'id_number', 'service_date', 'vat_number', 'vat_registered', 'commission_base') if kind == 'invoice' else ('deceased','id_number','date_in','time_in','driver','driver_in')
        if old['mf_key'] != mf or any(data.get(k) != record.get(k) for k in immutable):
            raise HTTPException(409, 'This document was already imported with different details. It cannot be replaced or paid again.')
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
    write_audit_log(db,actor_user_id=actor,franchise_user_id=fid,action='commission_document_reuploaded' if old else 'commission_document_saved',entity_type='commission_documents',entity_id=doc_id,new_values={'kind':kind,'record':record,'staff':[{'employee_user_id':uid,'role':role} for uid,role in staff]})
    return doc_id, bool(old)


class InvoiceStageIn(BaseModel):
    preview_token: str = Field(max_length=2000000)
    confirmed_franchise: bool = False


@router.post('/invoices/preview')
def preview_invoices(franchise_user_id: int | None = None, external_branch_id: int | None = None, files: list[UploadFile] = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db), expected_branch_id: int | None = None):
    fid = import_scope(db, current_user, franchise_user_id)
    if not 1 <= len(files) <= 30:
        raise HTTPException(400, 'Upload 1–30 MF Invoice PDFs per batch.')
    records, errors, size = [], [], 0
    try:
        for upload in files:
            name = PurePath((upload.filename or 'invoice.pdf').replace('\\', '/')).name[:255]
            content = upload.file.read(10 * 1024 * 1024 + 1); size += len(content)
            if len(content) > 10 * 1024 * 1024 or size > 50 * 1024 * 1024:
                raise HTTPException(400, 'Maximum 10 MB per PDF and 50 MB per batch.')
            try:
                parsed, failures = parse_invoice_pdf(content)
            except Exception:
                errors.append({'filename': name, 'error': 'Cannot read this invoice PDF.'}); continue
            digest = sha256(content).hexdigest()
            accepted = []
            for record in parsed:
                try:
                    record['earning_branch_id'] = check_import_branch(db, fid, record, external_branch_id,expected_branch_id)
                    from app.services.external_commissions import is_external
                    record['external_branch_id'] = record['earning_branch_id'] if is_external(db,fid,record['earning_branch_id']) else None
                except HTTPException as exc:
                    errors.append({'filename': name, 'page': record['page'], 'error': exc.detail}); continue
                record.update(filename=name, source_hash=digest); accepted.append(record)
            if accepted:
                from app.services.commission_files import store_file
                store_file(db,fid,digest,name,content,current_user.id,'invoice',imported_page_count(accepted))
                records.extend(accepted)
            errors.extend(dict(error, filename=name) for error in failures)
            if imported_page_count(records) + imported_page_count(errors) > 100:
                raise HTTPException(400, 'Import up to 100 pages per batch.')
        db.commit()
    except Exception:
        db.rollback(); raise
    return {'records': records, 'errors': errors, 'preview_token': signer().dumps({'kind': 'invoices', 'user_id': current_user.id, 'franchise_user_id': fid, 'records': records})}


@router.post('/invoices/stage')
def stage_invoices(payload: InvoiceStageIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db), background_tasks: BackgroundTasks = None):
    if not payload.confirmed_franchise:
        raise HTTPException(400, 'Confirm the invoice details and franchise first.')
    try:
        source = signer().loads(payload.preview_token, max_age=3600)
        if source.get('kind') != 'invoices' or source.get('user_id') != current_user.id:
            raise BadSignature('Wrong preview')
    except BadSignature:
        raise HTTPException(400, 'Invoice preview expired or invalid. Upload again.')
    fid = import_scope(db, current_user, source['franchise_user_id'])
    try:
        db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15015, 'fid': fid})
        ids, duplicates = [], 0
        for record in source['records']:
            if not db.execute(text('SELECT 1 FROM commission_document_files WHERE franchise_user_id=:fid AND source_hash=:hash'), {'fid': fid, 'hash': record['source_hash']}).scalar():
                raise HTTPException(400, 'Original invoice PDF is missing. Upload again.')
            doc_id, duplicate = save_document(db, fid, 'invoice', record, [], current_user.id)
            ids.append(doc_id); duplicates += duplicate
        write_audit_log(db, actor_user_id=current_user.id, franchise_user_id=fid, action='mf_invoices_staged', entity_type='commission_documents', new_values={'document_ids': ids})
        db.commit()
        if background_tasks is not None:
            from app.services.commission_automation import reconcile_holder
            background_tasks.add_task(reconcile_holder, fid)
        return {'document_ids': ids, 'saved': len(ids) - duplicates, 'duplicates': duplicates}
    except Exception:
        db.rollback(); raise


@router.get('/invoices/{document_id}/download')
def download_invoice(document_id: int, franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = import_scope(db, current_user, franchise_user_id)
    row = db.execute(text('''SELECT f.file_content FROM commission_documents d JOIN commission_document_files f
        ON f.franchise_user_id=d.franchise_user_id AND f.source_hash=d.source_hash
        WHERE d.id=:id AND d.franchise_user_id=:fid AND d.kind='invoice' '''), {'id': document_id, 'fid': fid}).mappings().first()
    if not row:
        raise HTTPException(404, 'Saved invoice PDF not found in this franchise.')
    write_audit_log(db,actor_user_id=current_user.id,franchise_user_id=fid,action='commission_document_downloaded',entity_type='commission_documents',entity_id=document_id)
    db.commit()
    return Response(content=bytes(row['file_content']), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="mf-invoice-{document_id}.pdf"', 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post('/preview')
def preview(franchise_user_id: int | None = None, external_branch_id: int | None = None, files: list[UploadFile] = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db), expected_branch_id: int | None = None):
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
        accepted=[]
        for record in parsed:
            try:
                record['earning_branch_id'] = check_import_branch(db, fid, record, external_branch_id,expected_branch_id)
                from app.services.external_commissions import is_external
                record['external_branch_id'] = record['earning_branch_id'] if is_external(db,fid,record['earning_branch_id']) else None
            except HTTPException as exc:
                errors.append({'filename': name, 'page': record['page'], 'error': exc.detail}); continue
            record.update(filename=name, source_hash=sha256(content).hexdigest()); records.append(record);accepted.append(record)
        if accepted:
            from app.services.commission_files import store_file
            store_file(db,fid,sha256(content).hexdigest(),name,content,current_user.id,'receipt',imported_page_count(accepted))
        errors.extend(dict(e, filename=name) for e in failures)
        if imported_page_count(records) + imported_page_count(errors) > 100:
            raise HTTPException(400, 'Import up to 100 pages per batch.')
    db.commit()
    return {'records': records, 'errors': errors, 'allocations':suggest_receipt_allocations(db,fid,records,current_user), 'preview_token': signer().dumps({'kind': 'receipts', 'user_id': current_user.id, 'franchise_user_id': fid, 'records': records})}


@router.post('/stage')
def stage(payload: StageIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db), background_tasks: BackgroundTasks = None):
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
    if not payload.allocations:
        payload = payload.model_copy(update={'allocations':[ReceiptAllocation(record=i,employee_user_ids=[]) for i in range(len(records))]})
    if {a.record for a in payload.allocations} != set(range(len(records))) or len(payload.allocations) != len(records):
        raise HTTPException(400, 'Check the employee selection for each receipt.')
    try:
        db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15015, 'fid': fid})
        ids, duplicates = [], 0
        for allocation in payload.allocations:
            staff = []
            for uid in set(allocation.employee_user_ids):
                person = import_participant(db, current_user, uid, fid)
                from app.services.external_commissions import permission_branch
                bid = require_branch(db, fid, records[allocation.record]['branch'], records[allocation.record].get('external_branch_id'))
                if person['franchise_user_id'] != fid or not enabled_for_branch(db, fid, uid, 'invoice_commission', permission_branch(db, fid, uid, bid)):
                    raise HTTPException(403, 'Select only active franchise employees enabled for MF File Receipts.')
                staff.append((uid, allocation.employee_roles.get(uid, 'driver')))
            doc_id, duplicate = save_document(db, fid, 'receipt', records[allocation.record], staff, current_user.id)
            ids.append(doc_id); duplicates += duplicate
        write_audit_log(db, actor_user_id=current_user.id, franchise_user_id=fid, action='mf_receipts_staged', entity_type='commission_documents', new_values={'document_ids': ids})
        db.commit()
        if background_tasks is not None:
            from app.services.commission_automation import reconcile_holder
            background_tasks.add_task(reconcile_holder, fid)
        return {'document_ids': ids, 'saved': len(ids) - duplicates, 'duplicates': duplicates}
    except Exception:
        db.rollback(); raise


@router.get('/documents')
def documents(franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = import_scope(db, current_user, franchise_user_id)
    rows = db.execute(text('SELECT id,kind,source_data,created_at FROM commission_documents WHERE franchise_user_id=:fid AND deleted_at IS NULL ORDER BY id DESC LIMIT 100'), {'fid': fid}).mappings().all()
    return [{'id': r['id'], 'kind': r['kind'], 'record': json.loads(r['source_data']), 'created_at': r['created_at']} for r in rows]


def calculate_plan(db, fid, ids, user):
    from sqlalchemy import bindparam
    selected = db.execute(text('SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND deleted_at IS NULL AND id IN :ids').bindparams(bindparam('ids', expanding=True)), {'fid': fid, 'ids': list(set(ids))}).mappings().all()
    if len(selected) != len(set(ids)):
        raise HTTPException(403, 'Document is outside this franchise.')
    cases = {(d['branch_key'], d['mf_key']) for d in selected}
    policies = policy_map(db, fid)
    result = []
    for bk, mf in sorted(cases):
        from app.services.external_commissions import external_branches, permission_branch, is_external
        matching_branches = [b for b in [*branches(db, fid), *external_branches(db, fid)] if branch_key(b['name']) == bk]
        if len(matching_branches) != 1:
            result.append({'mf': mf, 'branch': bk, 'state': 'blocked', 'reason': 'Document branch is no longer active in this holder group'})
            continue
        matched_branch = matching_branches[0]
        settings = receipt_settings(db, fid, matched_branch['id'])
        docs = db.execute(text('SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND branch_key=:branch AND mf_key=:mf AND deleted_at IS NULL ORDER BY id'), {'fid': fid, 'branch': bk, 'mf': mf}).mappings().all()
        books = [d for d in docs if d['kind'] == 'mortuary' and (d['branch_key'], d['mf_key']) == (bk, mf)]
        receipts = [d for d in docs if d['kind'] == 'receipt' and (d['branch_key'], d['mf_key']) == (bk, mf)]
        if not books or not receipts:
            result.append({'mf': mf, 'branch': bk, 'state': 'blocked', 'reason': 'Matching Mortuary Book missing' if not books else 'Matching MF File Receipt missing'})
            continue
        from app.services.receipt_commissions import require_payment_proof
        try:
            proof = require_payment_proof(db, fid, matched_branch['id'], mf)
        except HTTPException as exc:
            result.append({'mf': mf, 'branch': matched_branch['name'], 'state': 'blocked', 'reason': exc.detail})
            continue
        book = next(d for d in docs if d['id'] == proof['mortuary_document_id'])
        invoice = next(d for d in docs if d['id'] == proof['invoice_document_id'])
        book_data, invoice_data = json.loads(book['source_data']), json.loads(invoice['source_data'])
        receipts = [d for d in receipts if d['id'] in proof['receipt_document_ids']]
        for doc in [book, invoice]:
            data = json.loads(doc['source_data'])
            if doc['kind'] == 'invoice':
                people = db.execute(text("SELECT employee_user_id,CASE WHEN SUM(CASE WHEN removal_role='assistant' THEN 1 ELSE 0 END)>0 THEN 'assistant' ELSE 'driver' END AS removal_role FROM commission_document_staff WHERE document_id IN :ids GROUP BY employee_user_id ORDER BY employee_user_id").bindparams(bindparam('ids', expanding=True)), {'ids': proof['receipt_document_ids']}).mappings().all()
            else:
                people = db.execute(text('SELECT * FROM commission_document_staff WHERE document_id=:id ORDER BY employee_user_id'), {'id': doc['id']}).mappings().all()
            category = 'removals' if doc['kind'] == 'mortuary' else 'invoice_commission'
            matching_receipt = receipts[0]
            receipt = json.loads(matching_receipt['source_data'])
            identity_error = bool(book_data.get('id_number') and receipt.get('id_number') and book_data['id_number'] != receipt['id_number'])
            for staff in people:
                uid = staff['employee_user_id']
                line = {'mf': mf, 'branch': data['branch'], 'employee_user_id': uid, 'category': category,
                        'mortuary_document_id': book['id'], 'receipt_document_id': matching_receipt['id'],
                        'invoice_document_id': invoice['id'], 'invoice_number': invoice_data['invoice_number'],
                        'invoice_total': proof['invoice_total'], 'total_received': proof['total_received'],
                        'receipt_document_ids': proof['receipt_document_ids'],
                        'receipt_numbers': [json.loads(d['source_data'])['receipt_number'] for d in receipts],
                        'earning_branch_id': matched_branch['id'], 'earning_branch_name': matched_branch['name'],
                        'service_date': data['service_date'], 'deceased': receipt.get('deceased') or book_data.get('deceased'),
                        'id_number': receipt.get('id_number') or book_data.get('id_number'),
                        'receipt_number': receipt.get('receipt_number'), 'reference': book_data['reference'],
                        'gross_received': receipt.get('gross_received'), 'state': 'ready', 'reason': '', 'amount': None}
                person = None
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
                existing = db.execute(text("SELECT id FROM commission_entries WHERE employee_user_id=:uid AND commission_type=:type AND " + ('mortuary_document_id=:doc' if category == 'removals' else 'invoice_document_id=:doc')), {'uid': uid, 'type': category, 'doc': doc['id']}).scalar()
                if category == 'invoice_commission' and not existing:
                    historical = db.execute(text("SELECT id,reference,branch_name FROM commission_entries WHERE franchise_user_id=:fid AND employee_user_id=:uid AND commission_type='invoice_commission' AND invoice_document_id IS NULL"), {'fid': fid, 'uid': uid}).mappings().all()
                    existing = next((r['id'] for r in historical if mf_key(r['reference'].split(' / Receipt ', 1)[0]) == mf and branch_key(r['branch_name']) == bk), None)
                if existing:
                    line.update(state='already_recorded', reason='Commission already recorded')
                elif not options.get(category, {}).get('enabled'):
                    line.update(state='blocked', reason='Commission category disabled for this employee')
                elif not enabled_for_branch(db,fid,uid,category,permission_branch(db,fid,uid,matched_branch['id'])):
                    line.update(state='blocked',reason='Commission category disabled for this employee at this branch')
                elif identity_error:
                    line.update(state='blocked', reason='MF matches but deceased ID numbers differ')
                if not existing:
                    reference = book_data['reference'] if category == 'removals' else f"{book_data['reference']} / Invoice {invoice_data['invoice_number']}"
                    try:
                        _assert_not_duplicate(db, fid, uid, EntryIn(commission_type=category, service_date=data['service_date'], reference=reference[:255], branch_name=data['branch']))
                    except HTTPException as exc:
                        if exc.status_code != 409:
                            raise
                        line.update(state='already_recorded', reason='Matching commission already recorded manually')
                if category == 'removals':
                    policy = effective_policy(policies, uid)
                    from app.services.receipt_commissions import effective_branch_rates
                    overrides=effective_branch_rates(db,fid,uid,permission_branch(db,fid,uid,matched_branch['id']))
                    policy['rates'].update(overrides)
                    other_branch = branch_key(book_data['branch']) not in {branch_key(b['name']) for b in branches(db, fid)}
                    try:
                        fee = price_removal(book_data, staff['removal_role'] or 'driver', policy, effective_policy(policies, 0).get('extra_holidays', []), other_branch=False, staff_hours=person)
                    except (ValueError, TypeError):
                        line.update(state='blocked', reason='Correct the employee’s working hours in Edit Staff before calculating commission')
                        result.append(line)
                        continue
                    line.update(**fee, rate=fee['amount'], role=staff['removal_role'], notes=book_data)
                    if line['amount'] is None and line['state'] == 'ready':
                        line.update(state='blocked', reason='Removal fee not configured')
                else:
                    role = staff['removal_role'] or 'driver'
                    from app.services.receipt_commissions import invoice_commission_rate
                    rate=invoice_commission_rate(db,fid,uid,role,matched_branch['id'],policies,settings)
                    line.update(rate=str(rate) if rate is not None else None, vat_registered=proof['vat_registered'], vat_rate=proof['vat_rate'], vat_source=proof['vat_source'], vat_notice=proof['vat_notice'])
                    base = Decimal(proof['commission_base'])
                    line.update(base_amount=str(base), vat_number=proof.get('vat_number'), amount=str(money(base * Decimal(str(rate)) / 100)) if rate is not None else None)
                    if rate is None and line['state'] == 'ready':
                        line.update(state='blocked', reason='Receipt commission percentage not configured')
                result.append(line)
    from app.services.service_claims import surcharge_line
    seen_surcharges = set()
    for source in list(result):
        if source.get('category') not in {'removals', 'invoice_commission'} or source.get('state') not in {'ready', 'already_recorded'}:
            continue
        key = (source['employee_user_id'], source['invoice_document_id'])
        if key in seen_surcharges:
            continue
        seen_surcharges.add(key)
        try:
            extra = surcharge_line(db, user, fid, source['employee_user_id'], source.get('role') or 'driver', source['earning_branch_id'], source, source['service_date'], source['reference'])
            if extra:
                extra.update(employee_name=source.get('employee_name'), employee_branch_name=source.get('employee_branch_name'))
                result.append(extra)
        except HTTPException as exc:
            result.append({**source, 'category': 'service_other_branch', 'state': 'blocked', 'reason': exc.detail, 'amount': None})
    return result


def plan_digest(plan):
    return sha256(json.dumps(plan, sort_keys=True, default=str).encode()).hexdigest()


@router.post('/calculate')
def calculate(payload: CalculateIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = import_scope(db, current_user, payload.franchise_user_id)
    plan = calculate_plan(db, fid, payload.document_ids, current_user)
    return {'items': plan, 'total': str(sum((Decimal(r['amount']) for r in plan if r['state'] == 'ready'), Decimal(0))),
            'quote_token': signer().dumps({'kind': 'paired_commission_quote', 'user_id': current_user.id, 'fid': fid, 'ids': sorted(set(payload.document_ids)), 'digest': plan_digest(plan)})}




def store_ready_plan(db, fid, current_user, plan, automatic=False):
    ids = []
    for item in plan:
        if item['state'] != 'ready':
            continue
        from app.services.receipt_commissions import require_payment_proof
        require_payment_proof(db, fid, item['earning_branch_id'], item['reference'], item['mortuary_document_id'], item['receipt_document_id'], item['invoice_document_id'])
        item = {**item, 'automatic_approval': automatic}
        reference = item['reference'] if item['category'] == 'removals' else f"{item['reference']} / Invoice {item['invoice_number']}"
        notes = '\n'.join(f'{k}: {v}' for k, v in item.items() if k not in {'notes', 'state', 'reason'} and v is not None)
        if item.get('notes'):
            notes += '\n' + '\n'.join(f'{k}: {item["notes"].get(k, "-")}' for k in ('deceased', 'id_number', 'collected_at', 'driver_in', 'date_in', 'time_in'))
        entry = db.execute(text('''INSERT INTO commission_entries(franchise_user_id,employee_user_id,commission_type,service_date,reference,quantity,
            applied_rate,calculated_amount,invoice_value_before_tax,notes,branch_name,created_by_user_id,status,submitted_at,reviewed_at,
            reviewed_by_user_id,last_edited_by_user_id,mortuary_document_id,receipt_document_id,invoice_document_id,source_metadata,earning_branch_id)
            VALUES(:fid,:uid,:type,:day,:ref,1,:rate,:amount,:base,:notes,:branch,:actor,'approved',NOW(),NOW(),:reviewer,:actor,:book,:receipt,:invoice,:metadata,:earning_branch) RETURNING *'''),
            {'fid': fid, 'uid': item['employee_user_id'], 'type': item['category'], 'day': date.fromisoformat(item['service_date']), 'ref': reference[:255],
             'rate': Decimal(item['rate']), 'amount': Decimal(item['amount']), 'base': Decimal(item['base_amount']) if item.get('base_amount') is not None else None,
             'notes': notes, 'branch': item['branch'], 'actor': current_user.id, 'reviewer': None if automatic else current_user.id, 'book': item['mortuary_document_id'], 'receipt': item['receipt_document_id'], 'invoice': item['invoice_document_id'], 'metadata': json.dumps(item, default=str),'earning_branch':item['earning_branch_id']}).mappings().first()
        _audit(db, entry['id'], 'matched_documents_auto_approved' if automatic else 'matched_documents_commission', current_user.id, new=dict(entry))
        _notify(db, item['employee_user_id'], 'Matched commission added', f"{COMMISSION_LABELS[item['category']]} · {reference}", entry['id'], 'success')
        ids.append(entry['id'])
        write_audit_log(db,actor_user_id=current_user.id,franchise_user_id=fid,action='commission_allocated_automatically' if automatic else 'commission_allocated',entity_type='commission_documents',entity_id=item['invoice_document_id'] if item['category']=='invoice_commission' else item['mortuary_document_id'],new_values={'entry_id':entry['id'],'employee_user_id':item['employee_user_id'],'branch_id':item['earning_branch_id'],'amount':item['amount'],'category':item['category'],'invoice_document_id':item['invoice_document_id'],'receipt_document_ids':item.get('receipt_document_ids',[])})
    return ids

@router.post('/settle')
def settle(payload: CalculateIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.api.commission import _profile
    roles, _, _, _, _ = _profile(db, current_user)
    if not {'FranchiseUser', 'SuperUser'} & roles:
        raise HTTPException(403, 'Only the franchise holder may approve commission payouts.')
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
        ids = store_ready_plan(db, fid, current_user, plan)
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
        from app.services.commission_automation import default_report
        period = default_report(datetime.strptime(month, '%Y-%m'))
        first, last = period['period_start'], period['period_end']
    except ValueError:
        raise HTTPException(400, 'Select a valid report month.')
    rows = _rows(db, current_user, employee_user_id=employee_user_id, from_date=first, to_date=last, status='approved', franchise_user_id=fid)
    grouped = {}
    for row in rows:
        if not row['payment_eligible']:
            continue
        metadata = json.loads(row.get('source_metadata') or '{}')
        home = assignment(db, row['employee_user_id']) or {}
        bid = row.get('earning_branch_id') or metadata.get('earning_branch_id') or home.get('branch_id')
        if branch_id and bid != branch_id:
            continue
        branch_name = next((b['name'] for b in branches(db,fid,False) if b['id']==bid),None) or metadata.get('earning_branch_name') or home.get('branch_name') or 'Unassigned branch'
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
                data = [[para(x) for x in ('Date', 'MF / Invoice / Receipts / Branch', 'Deceased / ID', 'Total received', 'Commissionable amount', 'Fee / Rate', 'Commission')]]
                subtotal = Decimal(0)
                for row, meta in entries:
                    amount = money(row['calculated_amount']); subtotal += amount
                    values = [row['service_date'], f"{row['reference']}\n{row.get('carry_forward_notice') or ''}\nReceipts: {', '.join(meta.get('receipt_numbers', []))}\n{row.get('branch_name') or ''}", f"{meta.get('deceased') or '—'}\n{meta.get('id_number') or '—'}",
                              f"R {money(meta.get('total_received') or meta['gross_received']):,.2f}" if meta.get('total_received') or meta.get('gross_received') else '—',
                              f"R {money(row['invoice_value_before_tax']):,.2f}" if row.get('invoice_value_before_tax') is not None else '—',
                              f"{row['applied_rate']}%" if category == 'invoice_commission' else f"{row['applied_rate']}x" if category == 'overtime' and meta.get('calculation_type')!='fixed' else f"R {money(row['applied_rate']):,.2f}", f'R {amount:,.2f}']
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

