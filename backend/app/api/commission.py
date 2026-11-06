from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, EmailStr
from typing import Literal
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_user_role_names, get_current_franchise_user_id
from app.db.session import get_db
from app.models.core import User

router = APIRouter()
COMMISSION_TYPES = {"removals","grave_service","full_funeral_service","cremation_service","church_service","invoice_commission","joinings","overtime","service_other_branch"}


class DeliverySettingsIn(BaseModel):
    franchise_user_id: int | None = None
    recipient_email: EmailStr | None = None
    month_key: str = Field(pattern=r'^\d{4}-\d{2}$')
    period_start: date
    period_end: date
    send_on: datetime


def delivery_scope(db, user, fid):
    roles, _, _, _, _ = _profile(db, user)
    if not {'FranchiseUser', 'SuperUser'} & roles:
        raise HTTPException(403, 'Only the franchise holder can nominate finance recipients or change monthly dates.')
    selected = _franchise_scope(db, user, fid)
    if not selected:
        raise HTTPException(400, 'Select a franchise holder.')
    return selected


@router.get('/delivery-settings')
def delivery_settings(month: str | None = None, franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.commission_automation import default_report
    from app.services.email_service import get_email_config
    fid = delivery_scope(db, current_user, franchise_user_id)
    try:
        defaults = default_report(datetime.strptime(month, '%Y-%m') if month else None)
    except ValueError:
        raise HTTPException(400, 'Select a valid report month.')
    settings = db.execute(text('SELECT recipient_email FROM commission_delivery_settings WHERE franchise_user_id=:fid'), {'fid': fid}).mappings().first()
    report = db.execute(text('SELECT * FROM commission_monthly_reports WHERE franchise_user_id=:fid AND month_key=:month'), {'fid': fid, 'month': defaults['month_key']}).mappings().first()
    history = db.execute(text('''SELECT id,month_key,period_start,period_end,send_on,recipient_email,status,sent_at,error_message
        FROM commission_monthly_reports WHERE franchise_user_id=:fid ORDER BY month_key DESC LIMIT 12'''), {'fid': fid}).mappings().all()
    return {'recipient_email': settings['recipient_email'] if settings else None, 'report': dict(report) if report else defaults,
            'history': [dict(row) for row in history], 'email_configured': get_email_config().configured}


@router.put('/delivery-settings')
def save_delivery_settings(payload: DeliverySettingsIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.core.timezone import to_sa
    fid = delivery_scope(db, current_user, payload.franchise_user_id)
    try:
        datetime.strptime(payload.month_key, '%Y-%m')
    except ValueError:
        raise HTTPException(400, 'Select a valid report month.')
    send_on = to_sa(payload.send_on)
    if payload.period_start > payload.period_end or send_on.date() < payload.period_end:
        raise HTTPException(400, 'The cutoff must follow the start date, and the send date must be on or after the cutoff.')
    db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15016, 'fid': fid})
    status = db.execute(text('SELECT status FROM commission_monthly_reports WHERE franchise_user_id=:fid AND month_key=:month'), {'fid': fid, 'month': payload.month_key}).scalar()
    if status in {'sent', 'sending', 'uncertain'}:
        raise HTTPException(409, 'This report has already been sent or delivery needs checking. Its dates cannot be changed. Later approvals carry to the next unsent report.')
    db.execute(text('''INSERT INTO commission_delivery_settings(franchise_user_id,recipient_email,updated_by_user_id)
        VALUES(:fid,:email,:actor) ON CONFLICT(franchise_user_id) DO UPDATE SET recipient_email=EXCLUDED.recipient_email,
        updated_by_user_id=EXCLUDED.updated_by_user_id,updated_at=NOW()'''), {'fid': fid, 'email': str(payload.recipient_email).lower() if payload.recipient_email else None, 'actor': current_user.id})
    db.execute(text('''INSERT INTO commission_monthly_reports(franchise_user_id,month_key,period_start,period_end,send_on)
        VALUES(:fid,:month,:first,:last,:send) ON CONFLICT(franchise_user_id,month_key) DO UPDATE SET
        period_start=EXCLUDED.period_start,period_end=EXCLUDED.period_end,send_on=EXCLUDED.send_on,
        status='scheduled',error_message=NULL,next_attempt_at=NULL'''),
        {'fid': fid, 'month': payload.month_key, 'first': payload.period_start, 'last': payload.period_end, 'send': send_on})
    from app.services.audit import write_audit_log
    write_audit_log(db, actor_user_id=current_user.id, franchise_user_id=fid, action='commission_delivery_updated',
                    entity_type='commission_delivery_settings', new_values=payload.model_dump(mode='json'))
    db.commit()
    return {'saved': True}

class StructureIn(BaseModel):
    franchise_user_id: int | None = None
    commission_type: str
    label: str
    calculation_type: str = Field(pattern="^(fixed|percentage|overtime)$")
    rate: Decimal = Field(ge=0)
    overtime_multiplier: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True

class EntryIn(BaseModel):
    claim_deceased: str | None = Field(default=None, max_length=255)
    commission_role: Literal['driver', 'assistant'] = 'driver'
    employee_user_id: int | None = None
    commission_type: str
    service_date: date
    reference: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(default=1, gt=0)
    invoice_value_before_tax: Decimal | None = Field(default=None, ge=0)
    hours: Decimal | None = Field(default=None, ge=0)
    hourly_rate: Decimal | None = Field(default=None, ge=0)
    rate_override: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None
    branch_name: str | None = Field(default=None, max_length=255)
    earning_branch_id: int | None = Field(default=None, gt=0)

class ReviewIn(EntryIn):
    status: str = Field(pattern="^(approved|rejected)$")
    review_notes: str | None = None

class BulkReviewIn(BaseModel):
    entry_ids: list[int]
    status: str = Field(pattern="^(approved|rejected)$")
    review_notes: str | None = None


def _profile(db: Session, user: User):
    roles = set(get_user_role_names(db, user.id))
    if "FranchiseUser" in roles:
        return roles, get_current_franchise_user_id(db, user), None, None, "franchise"
    if "ManagerUser" in roles:
        row = db.execute(text("SELECT id, franchise_user_id FROM manager_users WHERE user_id=:uid AND COALESCE(is_active,TRUE)=TRUE"), {"uid": user.id}).mappings().first()
        return roles, int(row["franchise_user_id"]) if row and row["franchise_user_id"] else None, int(row["id"]) if row else None, user.id, "manager"
    if "EmployeeUser" in roles:
        row = db.execute(text("SELECT id, franchise_user_id, manager_user_id FROM employee_users WHERE user_id=:uid AND COALESCE(is_active,TRUE)=TRUE"), {"uid": user.id}).mappings().first()
        return roles, int(row["franchise_user_id"]) if row and row["franchise_user_id"] else None, int(row["manager_user_id"]) if row and row["manager_user_id"] else None, user.id, "employee"
    if "SuperUser" in roles:
        return roles, None, None, None, "super"
    raise HTTPException(403, "Commission access is not available for this account")


def _participant(db: Session, user: User, user_id: int, write: bool = False):
    roles, fid, manager_profile_id, own_user_id, kind = _profile(db, user)
    row = db.execute(text("""
        SELECT x.* FROM (
          SELECT e.user_id, e.franchise_user_id, e.manager_user_id, e.id AS employee_profile_id,
                 NULL::integer AS manager_profile_id, COALESCE(e.employee_role,'Employee') AS staff_role,
                 COALESCE(NULLIF(TRIM(CONCAT(COALESCE(e.name,''),' ',COALESCE(e.surname,''))),''),u.full_name) AS full_name,
                 e.employee_number, e.email, e.office_address_assigned, 'employee' AS staff_type
          FROM employee_users e JOIN users u ON u.id=e.user_id
          WHERE e.user_id=:uid AND COALESCE(e.is_active,TRUE)=TRUE AND COALESCE(u.is_active,TRUE)=TRUE
          UNION ALL
          SELECT m.user_id, m.franchise_user_id, NULL::integer, NULL::integer, m.id,
                 'Manager', COALESCE(NULLIF(TRIM(CONCAT(COALESCE(m.name,''),' ',COALESCE(m.surname,''))),''),u.full_name),
                 m.employee_number, m.email, m.office_address_assigned, 'manager'
          FROM manager_users m JOIN users u ON u.id=m.user_id
          WHERE m.user_id=:uid AND COALESCE(m.is_active,TRUE)=TRUE AND COALESCE(u.is_active,TRUE)=TRUE
        ) x LIMIT 1
    """), {"uid": user_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Staff member not found")
    if "SuperUser" in roles:
        return row
    if "FranchiseUser" in roles and int(row["franchise_user_id"] or 0) == int(fid or 0):
        return row
    if "ManagerUser" in roles:
        if int(row["user_id"]) == int(user.id):
            return row
        if row["staff_type"] == "employee" and int(row["manager_user_id"] or 0) == int(manager_profile_id or 0):
            return row
    if not write and own_user_id and int(row["user_id"]) == int(own_user_id):
        return row
    raise HTTPException(403, "Staff member is outside your commission scope")


def _calculate(structure, payload):
    qty = Decimal(payload.quantity)
    if payload.commission_type == "invoice_commission":
        if payload.invoice_value_before_tax is None:
            raise HTTPException(400, "Invoice value before tax is required")
        rate = Decimal(payload.rate_override if payload.rate_override is not None else structure["rate"])
        amount = Decimal(payload.invoice_value_before_tax) * rate / Decimal("100")
    elif payload.commission_type == "overtime":
        if payload.hours is None or payload.hourly_rate is None:
            raise HTTPException(400, "Overtime hours and hourly rate are required")
        rate = Decimal(payload.rate_override if payload.rate_override is not None else (structure["overtime_multiplier"] or structure["rate"] or 1))
        amount = Decimal(payload.hours) * Decimal(payload.hourly_rate) * rate
    else:
        if qty != qty.to_integral_value():
            raise HTTPException(400, "Quantity must be a whole number")
        rate = Decimal(payload.rate_override if payload.rate_override is not None else structure["rate"])
        amount = qty * rate
    return rate, amount.quantize(Decimal("0.01"))


def _notify(db, user_id, subject, message, entry_id, severity="info"):
    db.execute(text("""INSERT INTO notifications(user_id,recipient_user_id,notification_type,subject,message,status,is_read,severity,target_tab,related_table,related_id,created_at)
      VALUES(:uid,:uid,'commission',:subject,:message,'pending',FALSE,:severity,'commission','commission_entries',:entry,NOW())"""),
      {"uid": user_id, "subject": subject, "message": message, "severity": severity, "entry": entry_id})


def _reviewer_ids(db, participant):
    ids = []
    franchise_login = db.execute(text("SELECT user_id FROM franchise_users WHERE id=:id"), {"id": participant["franchise_user_id"]}).scalar()
    if franchise_login:
        ids.append(int(franchise_login))
    return list(dict.fromkeys(ids))


def _audit(db, entry_id, action, actor, old=None, new=None, note=None):
    db.execute(text("INSERT INTO commission_entry_audit(entry_id,action,actor_user_id,old_values,new_values,note) VALUES(:e,:a,:u,:o,:n,:note)"),
      {"e":entry_id,"a":action,"u":actor,"o":json.dumps(old,default=str) if old else None,"n":json.dumps(new,default=str) if new else None,"note":note})


def _franchise_scope(db: Session, current_user: User, requested_franchise_user_id: int | None):
    roles, fid, _, _, kind = _profile(db, current_user)
    if kind != "super":
        return fid
    if requested_franchise_user_id is None:
        return None
    exists = db.execute(text(
        "SELECT 1 FROM franchise_users WHERE id=:id AND COALESCE(is_active,TRUE)=TRUE"
    ), {"id": requested_franchise_user_id}).scalar()
    if not exists:
        raise HTTPException(404, "Franchise user not found")
    return requested_franchise_user_id


def _assert_review_allowed(db: Session, current_user: User, entry, participant):
    roles, _, manager_profile_id, _, kind = _profile(db, current_user)
    if entry["status"] != "pending" or entry.get("is_cancelled"):
        raise HTTPException(409, "Only a pending submission can be reviewed")
    if int(entry["employee_user_id"]) == int(current_user.id) or (kind not in {"franchise", "super"} and int(entry["created_by_user_id"]) == int(current_user.id)):
        raise HTTPException(403, "You cannot approve or reject your own submission")
    if kind == "manager":
        if participant["staff_type"] != "employee" or int(participant["manager_user_id"] or 0) != int(manager_profile_id or 0):
            raise HTTPException(403, "Managers may review only submissions from employees assigned to them")
    elif not ({"FranchiseUser", "SuperUser"} & roles):
        raise HTTPException(403, "Review access required")


def _assert_not_duplicate(db: Session, franchise_user_id: int, participant_user_id: int, payload: EntryIn, exclude_entry_id: int | None = None):
    params = {
        "fid": franchise_user_id, "employee": participant_user_id,
        "type": payload.commission_type, "date": payload.service_date,
        "reference": payload.reference,
    }
    exclude_clause = ""
    branch_clause = ""
    if payload.branch_name:
        branch_clause = "AND (COALESCE(TRIM(branch_name),'')='' OR LOWER(TRIM(branch_name))=LOWER(TRIM(:branch)))"
        params["branch"] = payload.branch_name
    if exclude_entry_id is not None:
        exclude_clause = "AND id<>:exclude_id"
        params["exclude_id"] = exclude_entry_id
    duplicate = db.execute(text(f"""
        SELECT id FROM commission_entries
        WHERE franchise_user_id=:fid AND employee_user_id=:employee
          AND commission_type=:type AND service_date=:date
          AND LOWER(TRIM(COALESCE(reference,'')))=LOWER(TRIM(:reference))
          AND COALESCE(is_cancelled,FALSE)=FALSE
          {exclude_clause}
          {branch_clause}
        LIMIT 1
    """), params).scalar()
    if duplicate:
        raise HTTPException(409, "This staff member already has a commission entry with the same type, date and reference")

@router.get('/types')
def types():
    return [{"value": x, "label": "MF File Receipts" if x == "invoice_commission" else x.replace('_',' ').title()} for x in sorted(COMMISSION_TYPES)]

@router.get('/employees')
def employees(franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles, fid, manager_profile_id, own_user_id, kind = _profile(db, current_user)
    fid = _franchise_scope(db, current_user, franchise_user_id)
    if kind == "super" and fid is None:
        return []
    params = {}
    conditions = ["COALESCE(active,TRUE)=TRUE"]
    conditions.append("franchise_user_id=:fid")
    params["fid"] = fid
    if kind == "manager":
        conditions.append("(staff_type='manager' AND user_id=:uid OR staff_type='employee' AND manager_user_id=:mid)")
        params.update({"uid": current_user.id, "mid": manager_profile_id})
    elif kind == "employee":
        conditions.append("user_id=:uid")
        params["uid"] = current_user.id
    rows = db.execute(text(f"""
      SELECT * FROM (
        SELECT e.user_id, e.franchise_user_id, e.manager_user_id, NULL::integer AS manager_profile_id, COALESCE(e.is_active,TRUE) active,
          COALESCE(NULLIF(TRIM(CONCAT(COALESCE(e.name,''),' ',COALESCE(e.surname,''))),''),u.full_name) full_name,
          e.employee_number, COALESCE(NULLIF(e.employee_role,''),'Employee') employee_role,
          COALESCE(NULLIF(e.email,''),u.email) email, e.office_address_assigned, 'employee' staff_type
        FROM employee_users e JOIN users u ON u.id=e.user_id WHERE COALESCE(u.is_active,TRUE)=TRUE
        UNION ALL
        SELECT m.user_id, m.franchise_user_id, NULL, m.id, COALESCE(m.is_active,TRUE),
          COALESCE(NULLIF(TRIM(CONCAT(COALESCE(m.name,''),' ',COALESCE(m.surname,''))),''),u.full_name),
          m.employee_number, 'Manager', COALESCE(NULLIF(m.email,''),u.email), m.office_address_assigned, 'manager'
        FROM manager_users m JOIN users u ON u.id=m.user_id WHERE COALESCE(u.is_active,TRUE)=TRUE
      ) staff WHERE {' AND '.join(conditions)} ORDER BY full_name
    """), params).mappings().all()
    return [dict(r) for r in rows]

def _ensure_default_structures(db: Session, fid: int, actor_user_id: int):
    defaults = [
        ("removals", "Removals", "fixed", Decimal("0"), None),
        ("grave_service", "Grave Service", "fixed", Decimal("0"), None),
        ("full_funeral_service", "Full Funeral Service", "fixed", Decimal("0"), None),
        ("cremation_service", "Cremation Service", "fixed", Decimal("0"), None),
        ("church_service", "Church Service", "fixed", Decimal("0"), None),
        ("joinings", "Joinings", "fixed", Decimal("0"), None),
        ("invoice_commission", "Invoice Commission", "percentage", Decimal("0"), None),
        ("overtime", "Overtime", "overtime", Decimal("0"), Decimal("1.5")),
    ]
    for commission_type, label, calculation_type, rate, multiplier in defaults:
        db.execute(text("""INSERT INTO commission_structures
          (franchise_user_id,commission_type,label,calculation_type,rate,overtime_multiplier,is_active,created_by_user_id,created_at,updated_at)
          VALUES(:fid,:type,:label,:calc,:rate,:mult,TRUE,:uid,NOW(),NOW())
          ON CONFLICT(franchise_user_id,commission_type) DO NOTHING"""),
          {"fid":fid,"type":commission_type,"label":label,"calc":calculation_type,"rate":rate,"mult":multiplier,"uid":actor_user_id})
    db.commit()

@router.get('/structures')
def structures(franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fid = _franchise_scope(db, current_user, franchise_user_id)
    if not fid:
        return []
    _ensure_default_structures(db, int(fid), current_user.id)
    return [dict(r) for r in db.execute(text("SELECT * FROM commission_structures WHERE franchise_user_id=:fid ORDER BY label"), {"fid": fid}).mappings().all()]

@router.post('/structures')
def save_structure(payload: StructureIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles, fid, _, _, _ = _profile(db, current_user)
    if "FranchiseUser" not in roles and "SuperUser" not in roles:
        raise HTTPException(403, "Only a franchise user can manage commission structures")
    if payload.commission_type not in COMMISSION_TYPES:
        raise HTTPException(400, "Invalid commission type")
    fid = _franchise_scope(db, current_user, payload.franchise_user_id)
    if not fid:
        raise HTTPException(400, "Select a franchise user before managing commission structures")
    row = db.execute(text("""INSERT INTO commission_structures(franchise_user_id,commission_type,label,calculation_type,rate,overtime_multiplier,is_active,created_by_user_id,updated_at)
      VALUES(:fid,:type,:label,:calc,:rate,:mult,:active,:uid,NOW()) ON CONFLICT(franchise_user_id,commission_type) DO UPDATE SET label=EXCLUDED.label,calculation_type=EXCLUDED.calculation_type,rate=EXCLUDED.rate,overtime_multiplier=EXCLUDED.overtime_multiplier,is_active=EXCLUDED.is_active,updated_at=NOW() RETURNING *"""),
      {"fid":fid,"type":payload.commission_type,"label":payload.label,"calc":payload.calculation_type,"rate":payload.rate,"mult":payload.overtime_multiplier,"active":payload.is_active,"uid":current_user.id}).mappings().first()
    db.commit()
    return dict(row)

@router.post('/claim-quote')
def claim_quote(payload: EntryIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles, _, _, _, kind = _profile(db, current_user)
    uid = current_user.id if kind in {'employee', 'manager'} else payload.employee_user_id
    if not uid:
        raise HTTPException(400, 'Select a staff member.')
    participant = _participant(db, current_user, uid, write=kind not in {'employee', 'manager'})
    from app.services.service_claims import calculate_claim
    return calculate_claim(db, current_user, payload, participant)


@router.post('/entries')
def create_entry(payload: EntryIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles, _, _, _, kind = _profile(db, current_user)
    own = kind in {'employee', 'manager'}
    uid = current_user.id if own else payload.employee_user_id
    if not uid:
        raise HTTPException(400, 'Staff member is required')
    participant = _participant(db, current_user, uid, write=not own)
    fid = participant['franchise_user_id']
    db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15015, 'fid': fid})
    from app.services.service_claims import calculate_claim, insert_surcharge
    quote = calculate_claim(db, current_user, payload, participant)
    status = 'approved' if quote['documents_valid'] else 'pending'
    proof = quote['proof'] if quote['documents_valid'] else {}
    metadata = {**proof, 'claim_deceased': payload.claim_deceased, 'commission_role': payload.commission_role,
                'claim_notice': quote['notice'], 'calculation_type': 'fixed', 'deceased': payload.claim_deceased, 'automatic_approval': quote['documents_valid']}
    reviewed_at = datetime.now() if status == 'approved' else None
    reviewed_by = None
    row = db.execute(text("""INSERT INTO commission_entries(franchise_user_id,employee_user_id,commission_type,service_date,
        reference,quantity,applied_rate,calculated_amount,notes,branch_name,created_by_user_id,status,submitted_at,
        reviewed_at,reviewed_by_user_id,last_edited_by_user_id,earning_branch_id,mortuary_document_id,receipt_document_id,invoice_document_id,source_metadata)
        VALUES(:fid,:uid,:type,:day,:ref,1,:rate,:rate,:notes,:branch,:actor,:status,NOW(),:reviewed_at,:reviewed_by,:actor,:bid,:book,:receipt,:invoice,:meta) RETURNING *"""),
        {'fid': fid, 'uid': uid, 'type': payload.commission_type, 'day': payload.service_date, 'ref': payload.reference.strip(),
         'rate': Decimal(quote['rate']), 'notes': payload.notes, 'branch': quote['branch_name'], 'actor': current_user.id,
         'status': status, 'reviewed_at': reviewed_at, 'reviewed_by': reviewed_by, 'bid': quote['branch_id'],
         'book': proof.get('mortuary_document_id'), 'receipt': proof.get('receipt_document_id'), 'invoice': proof.get('invoice_document_id'), 'meta': json.dumps(metadata, default=str)}).mappings().first()
    _audit(db, row['id'], 'service_claim_submitted' if status == 'pending' else 'service_claim_auto_approved', current_user.id, new=dict(row))
    if status == 'pending':
        for recipient in _reviewer_ids(db, participant):
            _notify(db, recipient, 'Service commission awaiting documents', f"{participant['full_name']} · {payload.commission_type} · MF {payload.reference}", row['id'], 'warning')
        if not quote['documents_valid']:
            notify_document_uploaders(db, fid, row['id'], payload.reference, quote['notice'])
    else:
        _notify(db, uid, 'Commission automatically approved', f"MF {payload.reference}: documents match and the invoice is fully paid.", row['id'], 'success')
        if quote['additional_fee']:
            insert_surcharge(db, current_user, quote['additional_fee'])
    db.commit()
    return {**dict(row), 'documents_valid': quote['documents_valid'], 'notice': quote['notice']}


def notify_document_uploaders(db, fid, entry_id, reference, reason):
    from app.services.attendance_branches import import_staff
    ids = [person['user_id'] for person in import_staff(db, fid) if person.get('can_import_commissions')]
    for uid in set(ids):
        _notify(db, uid, 'Document uploads required', f'MF {reference}: {reason}. Upload the closed file documents under Upload proof.', entry_id, 'warning')


def _rows(db, user, employee_user_id=None, from_date=None, to_date=None, status=None, search=None, franchise_user_id=None, earning_branch_id=None):
    roles, fid, manager_profile_id, own_user_id, kind = _profile(db, user)
    fid = _franchise_scope(db, user, franchise_user_id)
    where = ["1=1"]
    params = {}
    if kind == "super" and fid is None:
        return []
    if employee_user_id:
        participant = _participant(db, user, employee_user_id)
        if kind == "super" and int(participant["franchise_user_id"] or 0) != int(fid or 0):
            raise HTTPException(403, "Staff member is outside the selected franchise")
        where.append("c.employee_user_id=:employee")
        params["employee"] = employee_user_id
    elif kind == "franchise":
        where.append("c.franchise_user_id=:fid")
        params["fid"] = fid
    elif kind == "manager":
        # Keep the manager's own totals separate. Assigned employees are
        # requested explicitly through employee_user_id.
        where.append("c.employee_user_id=:uid")
        params["uid"] = user.id
    elif kind == "employee":
        where.append("c.employee_user_id=:uid")
        params["uid"] = user.id
    elif kind == "super":
        if fid is None:
            return []
        where.append("c.franchise_user_id=:fid")
        params["fid"] = fid
    if earning_branch_id:
        where.append("c.earning_branch_id=:earning_branch"); params["earning_branch"] = earning_branch_id
    if from_date:
        where.append("c.service_date>=:fd"); params["fd"] = from_date
    if to_date:
        where.append("c.service_date<=:td"); params["td"] = to_date
    if status:
        where.append("c.status=:status"); params["status"] = status
    if search:
        where.append("(LOWER(COALESCE(c.reference,'')) LIKE :q OR LOWER(u.full_name) LIKE :q OR LOWER(c.commission_type) LIKE :q)"); params["q"] = f"%{search.lower()}%"
    rows = db.execute(text(f"""SELECT c.*,u.full_name employee_name,
      COALESCE(ep.employee_number,mp.employee_number) employee_number, rv.full_name reviewer_name,
      CASE WHEN mp.id IS NOT NULL THEN 'Manager' ELSE COALESCE(ep.employee_role,'Employee') END staff_role
      FROM commission_entries c JOIN users u ON u.id=c.employee_user_id
      LEFT JOIN employee_users ep ON ep.user_id=c.employee_user_id
      LEFT JOIN manager_users mp ON mp.user_id=c.employee_user_id
      LEFT JOIN users rv ON rv.id=c.reviewed_by_user_id
      WHERE {' AND '.join(where)} ORDER BY CASE WHEN c.status='pending' THEN 0 ELSE 1 END,c.service_date DESC,c.id DESC"""), params).mappings().all()
    from app.services.receipt_commissions import payment_eligibility
    result = []
    for row in rows:
        meta = json.loads(row.get('source_metadata') or '{}')
        result.append({**dict(row), **payment_eligibility(db, row), 'claim_deceased': meta.get('claim_deceased'), 'commission_role': meta.get('commission_role', 'driver')})
    return result

@router.get('/entries')
def entries(employee_user_id:int|None=None,from_date:date|None=None,to_date:date|None=None,status:str|None=None,search:str|None=None,franchise_user_id:int|None=None,current_user:User=Depends(get_current_user),db:Session=Depends(get_db),earning_branch_id:int|None=None):
    rows = _rows(db,current_user,employee_user_id,from_date,to_date,status,search,franchise_user_id,earning_branch_id)
    from app.services.pending_removals import pending_rows
    pending_imports = pending_rows(db,_franchise_scope(db,current_user,franchise_user_id),current_user,employee_user_id,from_date,to_date,status,search,earning_branch_id)
    approved = [r for r in rows if r["status"] == "approved" and r["payment_eligible"]]
    total = sum((Decimal(r["calculated_amount"] or 0) for r in approved), Decimal(0))
    overtime = sum((Decimal(r["calculated_amount"] or 0) for r in approved if r["commission_type"] == "overtime"), Decimal(0))
    counts = {x: sum(1 for r in rows if r["status"] == x) for x in ["pending","approved","rejected","cancelled"]}
    return {"items":[dict(r) for r in rows],"pending_imports":pending_imports,"total":total,"commission_total":total-overtime,"overtime_total":overtime,"counts":counts}


@router.get('/entries/{entry_id}')
def entry_detail(entry_id:int,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    entry = db.execute(text("SELECT employee_user_id,franchise_user_id FROM commission_entries WHERE id=:id"), {"id":entry_id}).mappings().first()
    if not entry:
        raise HTTPException(404,"Entry not found")
    _participant(db,current_user,int(entry["employee_user_id"]))
    rows = _rows(
        db,current_user,
        employee_user_id=int(entry["employee_user_id"]),
        franchise_user_id=int(entry["franchise_user_id"]),
    )
    selected = next((row for row in rows if int(row["id"])==entry_id),None)
    if not selected:
        raise HTTPException(404,"Entry not found")
    return dict(selected)


def _review_service(entry_id, payload, user, db, automatic=False):
    roles, _, _, _, _ = _profile(db, user)
    if not {'FranchiseUser', 'SuperUser'} & roles:
        raise HTTPException(403, 'Only the franchise holder may approve or reject service claims.')
    old = db.execute(text('SELECT * FROM commission_entries WHERE id=:id'), {'id': entry_id}).mappings().first()
    if not old:
        raise HTTPException(404, 'Claim not found')
    participant = _participant(db, user, int(old['employee_user_id']), write=True)
    _assert_review_allowed(db, user, old, participant)
    db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15015, 'fid': old['franchise_user_id']})
    if payload.status == 'rejected':
        db.execute(text("UPDATE commission_entries SET status='rejected',review_notes=:note,reviewed_at=NOW(),reviewed_by_user_id=:actor WHERE id=:id"), {'note': payload.review_notes, 'actor': user.id, 'id': entry_id})
        _audit(db, entry_id, 'service_claim_rejected', user.id, old=dict(old), note=payload.review_notes)
    else:
        from app.services.service_claims import calculate_claim, insert_surcharge
        quote = calculate_claim(db, user, payload, participant, exclude_id=entry_id)
        if not quote['documents_valid']:
            raise HTTPException(400, quote['notice'])
        proof = quote['proof']
        meta = {**proof, 'claim_deceased': payload.claim_deceased, 'commission_role': payload.commission_role,
                'calculation_type': 'fixed', 'deceased': payload.claim_deceased, 'automatic_approval': automatic}
        updated = db.execute(text("""UPDATE commission_entries SET commission_type=:type,service_date=:day,reference=:ref,
            quantity=1,applied_rate=:rate,calculated_amount=:rate,notes=:notes,branch_name=:branch,earning_branch_id=:bid,
            status='approved',review_notes=:note,reviewed_at=NOW(),reviewed_by_user_id=:reviewer,last_edited_by_user_id=:actor,updated_at=NOW(),
            mortuary_document_id=:book,receipt_document_id=:receipt,invoice_document_id=:invoice,source_metadata=:meta WHERE id=:id RETURNING *"""),
            {'type': payload.commission_type, 'day': payload.service_date, 'ref': payload.reference.strip(), 'rate': Decimal(quote['rate']),
             'notes': payload.notes, 'branch': quote['branch_name'], 'bid': quote['branch_id'], 'note': payload.review_notes,
             'actor': user.id, 'reviewer': None if automatic else user.id, 'book': proof['mortuary_document_id'], 'receipt': proof['receipt_document_id'], 'invoice': proof['invoice_document_id'], 'meta': json.dumps(meta, default=str), 'id': entry_id}).mappings().first()
        _audit(db, entry_id, 'service_claim_auto_approved' if automatic else 'service_claim_approved', user.id, old=dict(old), new=dict(updated), note=payload.review_notes)
        if quote['additional_fee']:
            insert_surcharge(db, user, quote['additional_fee'])
    _notify(db, int(old['employee_user_id']), 'Commission automatically approved' if automatic else 'Service claim reviewed', f'MF {payload.reference}: {payload.status}.', entry_id, 'success' if payload.status == 'approved' else 'warning')
    return dict(db.execute(text('SELECT * FROM commission_entries WHERE id=:id'), {'id': entry_id}).mappings().one())


@router.put('/entries/{entry_id}/review')
def review(entry_id: int, payload: ReviewIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        result = _review_service(entry_id, payload, current_user, db)
        db.commit()
        return result
    except Exception:
        db.rollback(); raise


@router.post('/entries/bulk-review')
def bulk_review(payload: BulkReviewIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        done = []
        for entry_id in dict.fromkeys(payload.entry_ids):
            row = db.execute(text('SELECT * FROM commission_entries WHERE id=:id'), {'id': entry_id}).mappings().first()
            if not row:
                raise HTTPException(404, 'A selected claim no longer exists.')
            meta = json.loads(row.get('source_metadata') or '{}')
            values = {key: row[key] for key in EntryIn.model_fields if key in row}
            values.update(claim_deceased=meta.get('claim_deceased'), commission_role=meta.get('commission_role', 'driver'))
            request = ReviewIn(**values, status=payload.status, review_notes=payload.review_notes)
            _review_service(entry_id, request, current_user, db)
            done.append(entry_id)
        db.commit()
        return {'updated': done}
    except Exception:
        db.rollback(); raise


@router.delete('/entries/{entry_id}')
def delete_entry(entry_id:int,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    roles,_,_,_,_ = _profile(db,current_user)
    if "FranchiseUser" not in roles and "SuperUser" not in roles: raise HTTPException(403,"Only a franchise user can delete entries")
    row=db.execute(text("SELECT * FROM commission_entries WHERE id=:id"),{"id":entry_id}).mappings().first()
    if not row: raise HTTPException(404,"Entry not found")
    _participant(db,current_user,int(row["employee_user_id"]),write=True)
    if row["status"] == "approved":
        raise HTTPException(409, "Approved commission entries cannot be cancelled")
    updated = db.execute(text("""UPDATE commission_entries
      SET status='cancelled',is_cancelled=TRUE,cancelled_at=NOW(),cancelled_by_user_id=:uid,
          last_edited_by_user_id=:uid,updated_at=NOW() WHERE id=:id RETURNING *"""),
      {"uid":current_user.id,"id":entry_id}).mappings().first()
    _audit(db,entry_id,"cancelled",current_user.id,old=dict(row),new=dict(updated))
    db.commit(); return {"ok":True,"status":"cancelled"}


@router.get('/entries/{entry_id}/history')
def entry_history(entry_id:int,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    entry = db.execute(text("SELECT * FROM commission_entries WHERE id=:id"), {"id": entry_id}).mappings().first()
    if not entry:
        raise HTTPException(404, "Entry not found")
    _participant(db, current_user, int(entry["employee_user_id"]))
    rows = db.execute(text("""SELECT a.*,u.full_name actor_name
      FROM commission_entry_audit a JOIN users u ON u.id=a.actor_user_id
      WHERE a.entry_id=:id ORDER BY a.created_at DESC,a.id DESC"""), {"id": entry_id}).mappings().all()
    return [dict(row) for row in rows]


def _pdf(rows,title):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image
    buf=BytesIO();styles=getSampleStyleSheet();doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=14*mm)
    logo=Path(__file__).resolve().parents[1]/'static'/'logo.png'; company=Paragraph('<b>Attendance Register Platform</b><br/>Commission Administration',styles['Normal'])
    logo_flow=Image(str(logo),width=48*mm,height=18*mm,kind='proportional') if logo.exists() else Paragraph('<b>COMPANY LOGO</b>',styles['Heading2'])
    header=Table([[company,logo_flow]],colWidths=[120*mm,60*mm]);header.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LINEBELOW',(0,0),(-1,-1),1,colors.HexColor('#333333'))]))
    story=[header,Spacer(1,5*mm),Paragraph(title,styles['Title']),Paragraph(f"Generated: {datetime.now().strftime('%d %B %Y %H:%M')}",styles['Normal']),Spacer(1,4*mm)]
    data=[["Date","Staff","Type","Reference","Status","Details","Amount"]];total=Decimal(0)
    for r in rows:
        amount=Decimal(r['calculated_amount'] or 0)
        if r['status']=='approved' and r.get('payment_eligible'): total+=amount
        metadata = json.loads(r.get('source_metadata') or '{}')
        details=f"{r['hours']} hrs x R{r['hourly_rate']} x {r['applied_rate']}" if r['commission_type']=='overtime' and metadata.get('calculation_type') != 'fixed' else (f"Invoice R{r['invoice_value_before_tax']} @ {r['applied_rate']}%" if r['commission_type']=='invoice_commission' else f"Qty {r['quantity']} @ R{r['applied_rate']}")
        if metadata.get('claim_deceased'):
            details += f" / {metadata['claim_deceased']} / {'Assistant' if metadata.get('commission_role') == 'assistant' else 'Employee'}"
        data.append([str(r['service_date']),r.get('employee_name',''),r['commission_type'].replace('_',' ').title(),(r['reference'] or '') + (' / ' + r['branch_name'] if r.get('branch_name') else ''),('Blocked: documents required' if r['status'] in {'approved','pending'} and not r.get('payment_eligible') else r['status'].title()),details,f"R {amount:,.2f}"])
    awaiting=sum((Decimal(str(r.get('expected_amount',r.get('calculated_amount')) or 0)) for r in rows if r['status'] in {'pending','approved'} and not r.get('payment_eligible')))
    data.append(["","","","","","AWAITING DOCUMENT CHECKS",f"R {awaiting:,.2f}"])
    data.append(["","","","","","APPROVED TOTAL",f"R {total:,.2f}"])
    from xml.sax.saxutils import escape
    styles['BodyText'].fontSize = 7
    styles['BodyText'].leading = 9
    data = [[Paragraph(escape(str(cell)), styles['BodyText']) for cell in row] for row in data]
    table=Table(data,colWidths=[18*mm,25*mm,25*mm,26*mm,22*mm,49*mm,21*mm],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8edf3')),('GRID',(0,0),(-1,-1),.35,colors.grey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(-2,-1),(-1,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(-1,1),(-1,-1),'RIGHT')]))
    story.extend([table,Spacer(1,8*mm),Paragraph('Authorisation',styles['Heading3']),Paragraph('Approved by: ______________________________    Date: ____________________',styles['Normal'])]);doc.build(story);buf.seek(0);return buf

@router.get('/report.pdf')
def report_pdf(employee_user_id:int|None=Query(default=None),from_date:date|None=None,to_date:date|None=None,status:str|None=None,franchise_user_id:int|None=None,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    rows=_rows(db,current_user,employee_user_id,from_date,to_date,status,franchise_user_id=franchise_user_id)
    from app.services.pending_removals import pending_rows
    rows+=pending_rows(db,_franchise_scope(db,current_user,franchise_user_id),current_user,employee_user_id,from_date,to_date,status)
    return StreamingResponse(_pdf(rows,"Staff Commission & Overtime Report"),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename=commission-overtime-report.pdf'})

@router.get('/entries/{entry_id}/form.pdf')
def form_pdf(entry_id:int,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    entry=db.execute(text("SELECT employee_user_id,franchise_user_id FROM commission_entries WHERE id=:id"),{"id":entry_id}).mappings().first()
    if not entry: raise HTTPException(404,"Entry not found")
    selected=[r for r in _rows(db,current_user,int(entry["employee_user_id"]),franchise_user_id=int(entry["franchise_user_id"])) if int(r['id'])==entry_id]
    if not selected: raise HTTPException(404,"Entry not found")
    return StreamingResponse(_pdf(selected,"Commission Review Form"),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename=commission-form-{entry_id}.pdf'})
