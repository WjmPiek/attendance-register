from datetime import datetime
import base64
import io
import zipfile
from pathlib import Path
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.core import User, UserRole
from app.services.audit import write_audit_log

from app.core.security import hash_password

router = APIRouter()

EMPLOYEE_ROLES = [
    "Finance",
    "Admin",
    "Arrangement Officer",
    "Driver",
    "Cleaner",
    "Mortuary Assistant",
    "Garden Cleaner",
    "Tea Lady",
]


class CreateManagerRequest(BaseModel):
    employee_number: str | None = None
    username: str | None = None
    name: str
    surname: str
    id_number: str | None = None
    email: EmailStr | None = None
    contact_number: str | None = None
    office_address_assigned: str | None = None
    work_start_time: str | None = '08:00'
    work_end_time: str | None = '17:00'
    office_area_id: int | None = None
    password: str | None = None


class CreateEmployeeRequest(BaseModel):
    username: str | None = None
    employee_number: str | None = None
    employee_role: str
    name: str
    surname: str
    id_number: str | None = None
    email: EmailStr | None = None
    contact_number: str | None = None
    office_address_assigned: str | None = None
    work_start_time: str | None = '08:00'
    work_end_time: str | None = '17:00'
    manager_user_id: int | None = None
    office_area_id: int | None = None
    password: str | None = None


class UpdateManagerRequest(BaseModel):
    employee_number: str | None = None
    username: str | None = None
    name: str | None = None
    surname: str | None = None
    id_number: str | None = None
    email: EmailStr | None = None
    contact_number: str | None = None
    office_address_assigned: str | None = None
    work_start_time: str | None = '08:00'
    work_end_time: str | None = '17:00'
    office_area_id: int | None = None
    password: str | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=8)


class UpdateEmployeeRequest(BaseModel):
    username: str | None = None
    employee_number: str | None = None
    employee_role: str | None = None
    name: str | None = None
    surname: str | None = None
    id_number: str | None = None
    email: EmailStr | None = None
    contact_number: str | None = None
    office_address_assigned: str | None = None
    work_start_time: str | None = '08:00'
    work_end_time: str | None = '17:00'
    manager_user_id: int | None = None
    office_area_id: int | None = None
    password: str | None = None
    is_active: bool | None = None


def _roles(db: Session, user: User) -> list[str]:
    return [ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]


def _hash_password(raw_password: str) -> str:
    # Use the same hashing helper used by /api/auth/login verification.
    # This makes reset passwords immediately usable for login.
    return hash_password(raw_password)


def _role_id(db: Session, name: str) -> int:
    row = db.execute(text("SELECT id FROM roles WHERE name = :name"), {"name": name}).mappings().first()
    if not row:
        raise HTTPException(status_code=500, detail=f"{name} role not found")
    return row["id"]




def _area_row(db: Session, area_id: int | None):
    if not area_id:
        return None
    row = db.execute(text("""
        SELECT id, name, latitude, longitude, allowed_radius_m
        FROM areas
        WHERE id = :area_id
    """), {"area_id": area_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=400, detail="Selected office location was not found")
    return row


def _assign_office_gps(db: Session, user_id: int, area_id: int | None):
    area = _area_row(db, area_id)
    if not area:
        return
    db.execute(text("""
        UPDATE gps_allocations_per_user
        SET is_active = FALSE, updated_at = :now
        WHERE user_id = :user_id
    """), {"user_id": user_id, "now": datetime.utcnow()})
    db.execute(text("""
        INSERT INTO gps_allocations_per_user (
            user_id, area_id, latitude, longitude, radius_meters, is_active, created_at, updated_at
        ) VALUES (
            :user_id, :area_id, :latitude, :longitude, :radius_meters, TRUE, :now, :now
        )
    """), {
        "user_id": user_id,
        "area_id": area["id"],
        "latitude": str(area["latitude"]) if area["latitude"] is not None else None,
        "longitude": str(area["longitude"]) if area["longitude"] is not None else None,
        "radius_meters": area["allowed_radius_m"] or 100,
        "now": datetime.utcnow(),
    })


def _franchise_profile_id(db: Session, user_id: int) -> int:
    row = db.execute(text("""
        SELECT id
        FROM franchise_users
        WHERE user_id = :user_id
        AND COALESCE(is_active, TRUE) = TRUE
    """), {"user_id": user_id}).mappings().first()

    if not row:
        raise HTTPException(status_code=403, detail="No active franchise profile found for this user")

    return row["id"]


def _require_franchise(db: Session, user: User) -> int:
    names = _roles(db, user)
    if "FranchiseUser" not in names:
        raise HTTPException(status_code=403, detail="Only FranchiseUser can create managers/employees")
    return _franchise_profile_id(db, user.id)


def _is_superuser(db: Session, user: User) -> bool:
    return "SuperUser" in _roles(db, user)


def _safe_email(prefix: str, name: str, surname: str) -> str:
    clean_name = "".join(ch.lower() for ch in (name or "staff") if ch.isalnum()) or "staff"
    clean_surname = "".join(ch.lower() for ch in (surname or "user") if ch.isalnum()) or "user"
    stamp = int(datetime.utcnow().timestamp() * 1000)
    return f"{prefix}.{clean_name}.{clean_surname}.{stamp}@no-email.local"





def _safe_username(prefix: str, name: str, surname: str) -> str:
    clean_name = "".join(ch.lower() for ch in (name or "staff") if ch.isalnum()) or "staff"
    clean_surname = "".join(ch.lower() for ch in (surname or "user") if ch.isalnum()) or "user"
    return f"{prefix}_{clean_name}_{clean_surname}"


def _table_exists(db: Session, table_name: str) -> bool:
    row = db.execute(text("SELECT to_regclass(:table_name) AS table_exists"), {"table_name": table_name}).mappings().first()
    return bool(row and row.get("table_exists"))


def _table_columns(db: Session, table_name: str) -> set[str]:
    if not _table_exists(db, table_name):
        return set()
    rows = db.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table_name
    """), {"table_name": table_name}).mappings().all()
    return {str(r["column_name"]) for r in rows}


def _delete_where(db: Session, table_name: str, where_sql: str, params: dict) -> int:
    if not _table_exists(db, table_name):
        return 0
    result = db.execute(text(f"DELETE FROM {table_name} WHERE {where_sql}"), params)
    return result.rowcount or 0



def _staff_identity_values(db: Session, staff_type: str, staff_id: int, user_id: int) -> dict:
    values = {"user_id": user_id, "staff_id": staff_id, "staff_type": staff_type}
    full_name = ""
    email = ""
    username = ""
    user_row = db.execute(text("SELECT full_name, email, username FROM users WHERE id = :user_id"), values).mappings().first()
    if user_row:
        full_name = str(user_row.get("full_name") or "").strip()
        email = str(user_row.get("email") or "").strip()
        username = str(user_row.get("username") or "").strip()
    table = "employee_users" if staff_type == "employee" else "manager_users"
    cols = _table_columns(db, table)
    select_cols = [c for c in ("name", "surname", "employee_number", "manager_code") if c in cols]
    if select_cols:
        row = db.execute(text(f"SELECT {', '.join(select_cols)} FROM {table} WHERE id = :staff_id"), values).mappings().first()
        if row:
            combined = (str(row.get("name") or "").strip() + " " + str(row.get("surname") or "").strip()).strip()
            if combined:
                full_name = combined
            username = username or str(row.get("employee_number") or row.get("manager_code") or "").strip()
    values.update({"full_name": full_name if len(full_name) >= 3 else "", "email": email, "username": username})
    return values


def _cleanup_notifications_for_removed_staff(db: Session, params: dict) -> int:
    if not _table_exists(db, "notifications"):
        return 0
    result = db.execute(text("""
        DELETE FROM notifications n
        WHERE n.user_id = :user_id
           OR n.recipient_user_id = :user_id
           OR (n.related_table = 'attendance_events' AND n.related_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM attendance_events ae WHERE ae.id = n.related_id))
           OR (n.related_table = 'leave_applications' AND n.related_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM leave_applications la WHERE la.id = n.related_id))
           OR (n.related_table = 'irp5_documents' AND n.related_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM irp5_documents doc WHERE doc.id = n.related_id))
           OR (:full_name <> '' AND (n.subject ILIKE '%' || :full_name || '%' OR n.message ILIKE '%' || :full_name || '%'))
           OR (:email <> '' AND (n.subject ILIKE '%' || :email || '%' OR n.message ILIKE '%' || :email || '%' OR n.recipient_email = :email))
           OR (:username <> '' AND (n.subject ILIKE '%' || :username || '%' OR n.message ILIKE '%' || :username || '%'))
    """), params)
    return result.rowcount or 0

def _delete_staff_related_records(db: Session, staff_type: str, staff_id: int, user_id: int) -> dict:
    """Remove all tab-visible data for a deleted employee or manager.

    The staff row and login are still deactivated by the caller so foreign-key safety is preserved,
    but attendance history/approvals, overview alerts, leave, payroll and IRP5 documents are removed.
    Column checks keep this compatible with older installs that may not have every optional column yet.
    """
    deleted = {
        "overview": 0,
        "history": 0,
        "approvals": 0,
        "hr_staff": 1,
        "leave": 0,
        "payroll": 0,
        "irp5": 0,
        "manager_assignments": 0,
    }
    params = _staff_identity_values(db, staff_type, staff_id, user_id)

    # History and approvals are both stored in attendance_events.
    if _table_exists(db, "attendance_events"):
        result = db.execute(text("DELETE FROM attendance_events WHERE user_id = :user_id"), params)
        count = result.rowcount or 0
        deleted["history"] += count
        deleted["approvals"] += count
        deleted["overview"] += count

    # Overview/system alert data that can keep deleted staff visible.
    if _table_exists(db, "notifications"):
        result = db.execute(text("""
            DELETE FROM notifications
            WHERE user_id = :user_id
               OR recipient_user_id = :user_id
        """), params)
        count = result.rowcount or 0
        deleted["overview"] += count

    leave_cols = _table_columns(db, "leave_applications")
    if leave_cols:
        conditions = []
        if "applicant_user_id" in leave_cols:
            conditions.append("applicant_user_id = :user_id")
        if staff_type == "employee" and "employee_user_id" in leave_cols:
            conditions.append("employee_user_id = :staff_id")
        if staff_type == "manager" and "manager_user_id" in leave_cols:
            conditions.append("manager_user_id = :staff_id")
        if conditions:
            result = db.execute(text("DELETE FROM leave_applications WHERE " + " OR ".join(conditions)), params)
            deleted["leave"] += result.rowcount or 0
            deleted["overview"] += result.rowcount or 0

    if _table_exists(db, "leave_balances"):
        result = db.execute(text("DELETE FROM leave_balances WHERE user_id = :user_id"), params)
        deleted["leave"] += result.rowcount or 0

    payroll_rows_cols = _table_columns(db, "payroll_import_rows")
    if "matched_user_id" in payroll_rows_cols:
        result = db.execute(text("DELETE FROM payroll_import_rows WHERE matched_user_id = :user_id"), params)
        deleted["payroll"] += result.rowcount or 0

    for table_name in ("payroll_runs", "payroll_settings"):
        cols = _table_columns(db, table_name)
        if "user_id" in cols:
            result = db.execute(text(f"DELETE FROM {table_name} WHERE user_id = :user_id"), params)
            deleted["payroll"] += result.rowcount or 0

    irp5_cols = _table_columns(db, "irp5_documents")
    if irp5_cols:
        conditions = []
        if "target_user_id" in irp5_cols:
            conditions.append("target_user_id = :user_id")
        if staff_type == "employee" and "employee_user_id" in irp5_cols:
            conditions.append("employee_user_id = :staff_id")
        if staff_type == "manager" and "manager_user_id" in irp5_cols:
            conditions.append("manager_user_id = :staff_id")
        if "target_staff_type" in irp5_cols and "target_staff_id" in irp5_cols:
            conditions.append("(target_staff_type = :staff_type AND target_staff_id = :staff_id)")
        if conditions:
            irp5_rows = db.execute(text("""
                SELECT id, stored_filename
                FROM irp5_documents
                WHERE """ + " OR ".join(conditions)), params).mappings().all()
            if irp5_rows:
                db.execute(text("DELETE FROM irp5_documents WHERE " + " OR ".join(conditions)), params)
                deleted["irp5"] += len(irp5_rows)
                upload_dir = Path(__file__).resolve().parents[2] / 'uploads' / 'irp5'
                for doc in irp5_rows:
                    stored_filename = doc.get('stored_filename')
                    if stored_filename:
                        try:
                            path = upload_dir / Path(stored_filename).name
                            if path.exists():
                                path.unlink()
                        except OSError:
                            pass

    # Remove office/location assignments and detach employees from deleted managers.
    if _table_exists(db, "gps_allocations_per_user"):
        deleted["overview"] += _delete_where(db, "gps_allocations_per_user", "user_id = :user_id", params)
    if staff_type == "manager" and _table_exists(db, "employee_users"):
        result = db.execute(text("""
            UPDATE employee_users
            SET manager_user_id = NULL, updated_at = :now
            WHERE manager_user_id = :staff_id
        """), {**params, "now": datetime.utcnow()})
        deleted["manager_assignments"] += result.rowcount or 0

    final_notification_cleanup = _cleanup_notifications_for_removed_staff(db, params)
    deleted["overview"] += final_notification_cleanup

    return deleted


def _delete_employee_related_records(db: Session, employee_id: int, user_id: int) -> dict:
    return _delete_staff_related_records(db, "employee", employee_id, user_id)


def _delete_manager_related_records(db: Session, manager_id: int, user_id: int) -> dict:
    return _delete_staff_related_records(db, "manager", manager_id, user_id)

def _unique_username(db: Session, base: str) -> str:
    base = (base or "staff_user").strip("_")[:70] or "staff_user"
    candidate = base
    counter = 1
    while db.execute(text("SELECT 1 FROM users WHERE username = :username"), {"username": candidate}).first():
        counter += 1
        candidate = f"{base}_{counter}"
    return candidate


def _ensure_user_login_columns(db: Session):
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100) UNIQUE"))
    db.execute(text("ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(500) NULL"))


def _staff_qr_target(db: Session, franchise_user_id: int | None, office_address: str | None = None) -> str:
    """QR target: franchise website first, otherwise office address in Google Maps."""
    website = None
    franchise_office = None
    if franchise_user_id:
        row = db.execute(text("""
            SELECT website, office_address
            FROM franchise_users
            WHERE id = :fid
            LIMIT 1
        """), {"fid": franchise_user_id}).mappings().first()
        if row:
            website = (row.get("website") or "").strip()
            franchise_office = (row.get("office_address") or "").strip()
    if website:
        if not website.lower().startswith(("http://", "https://")):
            website = "https://" + website
        return website
    address = (office_address or franchise_office or "").strip()
    if address:
        return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(address)
    return "https://martinsdirect.com"


def _qr_png_data_url(payload: str, pixels: int = 240) -> str | None:
    try:
        import qrcode
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        img = img.resize((pixels, pixels))
        out = io.BytesIO()
        img.save(out, format="PNG")
        return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        return None


def _ensure_profile_photo_columns(db: Session):
    """Request-time compatibility only. Prefer running the SQL file in DBeaver."""
    _ensure_user_login_columns(db)
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL"))
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL"))
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL"))
    db.execute(text("ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL"))
    db.execute(text("ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL"))
    db.execute(text("ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL"))
    db.execute(text("ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL"))
    db.execute(text("ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL"))
    db.execute(text("ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL"))
    db.commit()


def _scope_staff_row(db: Session, current_user: User, staff_type: str, staff_id: int):
    if staff_type not in {'employees', 'managers'}:
        raise HTTPException(status_code=400, detail='staff_type must be employees or managers')
    table = 'employee_users' if staff_type == 'employees' else 'manager_users'
    row = db.execute(text(f"""
        SELECT s.*, u.full_name AS login_full_name, u.email AS login_email,
               fu.franchise_name, fu.business_name, fu.website, fu.office_address
        FROM {table} s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN franchise_users fu ON fu.id = s.franchise_user_id
        WHERE s.id = :staff_id
        LIMIT 1
    """), {'staff_id': staff_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail='Staff member not found')
    roles = set(_roles(db, current_user))
    if 'SuperUser' in roles:
        return dict(row)
    franchise_user_id = _require_franchise(db, current_user)
    if int(row['franchise_user_id']) != int(franchise_user_id):
        raise HTTPException(status_code=403, detail='Staff member is outside your franchise')
    return dict(row)



def _photo_data_url(photo_bytes, mime='image/png'):
    if not photo_bytes:
        return None
    try:
        return f"data:{mime or 'image/png'};base64," + base64.b64encode(bytes(photo_bytes)).decode('ascii')
    except Exception:
        return None


def _public_staff_dict(row):
    data = dict(row)
    photo = data.pop('profile_photo', None)
    mime = data.pop('profile_photo_mime', None) or 'image/png'
    data['photo_url'] = _photo_data_url(photo, mime)
    return data

def _prepare_cropped_photo_bytes(photo_bytes, target_ratio=0.78):
    """Return image bytes cropped to the same portrait ratio used by the ID-photo placeholder.
    If the frontend has already saved the aligned crop, this keeps it unchanged; if an older full image
    exists in the DB, this prevents wide/full photos from printing on ID cards/PDF exports.
    """
    if not photo_bytes:
        return None
    try:
        from PIL import Image as PILImage
        source = PILImage.open(io.BytesIO(bytes(photo_bytes))).convert('RGB')
        w, h = source.size
        current_ratio = w / h if h else target_ratio
        if abs(current_ratio - target_ratio) > 0.02:
            if current_ratio > target_ratio:
                new_w = int(h * target_ratio)
                left = max(0, int((w - new_w) / 2))
                source = source.crop((left, 0, left + new_w, h))
            else:
                new_h = int(w / target_ratio)
                top = max(0, int((h - new_h) / 2))
                source = source.crop((0, top, w, top + new_h))
        out = io.BytesIO()
        source.save(out, format='PNG')
        return out.getvalue()
    except Exception:
        return bytes(photo_bytes)


def _photo_flowable(photo_bytes, width_mm=23, height_mm=19):
    """Return a ReportLab image that is cropped and forced to stay inside the ID photo box.

    The PDF card body row is intentionally compact. The previous 23x29mm photo was taller
    than the row, so ReportLab drew the image outside the bordered photo block. This version
    crops the source to the same ratio as the visible box and sizes it to fit inside that box.
    """
    if not photo_bytes:
        return None
    try:
        from reportlab.lib.units import mm
        from reportlab.platypus import Image
        cropped = _prepare_cropped_photo_bytes(photo_bytes, target_ratio=float(width_mm) / float(height_mm))
        img = Image(io.BytesIO(cropped), width=width_mm*mm, height=height_mm*mm)
        img.hAlign = 'CENTER'
        return img
    except Exception:
        return None


def _id_qr_drawing(payload: str, size_mm=24):
    from reportlab.lib.units import mm
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing
    qr_code = qr.QrCodeWidget(payload)
    bounds = qr_code.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    size = size_mm * mm
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(qr_code)
    return drawing


def _id_card_staff_rows(db: Session, current_user: User, franchise_id: int | None = None, staff_type: str | None = None, staff_id: int | None = None):
    roles = set(_roles(db, current_user))
    params = {}
    where_manager = 'COALESCE(mu.is_active, TRUE) = TRUE'
    where_employee = 'COALESCE(eu.is_active, TRUE) = TRUE'
    if staff_id is not None:
        if staff_type == 'managers':
            where_manager += ' AND mu.id = :staff_id'
            where_employee += ' AND 1 = 0'
        elif staff_type == 'employees':
            where_employee += ' AND eu.id = :staff_id'
            where_manager += ' AND 1 = 0'
        else:
            raise HTTPException(status_code=400, detail='staff_type must be managers or employees')
        params['staff_id'] = staff_id
    if 'SuperUser' in roles and franchise_id:
        where_manager += ' AND mu.franchise_user_id = :franchise_id'
        where_employee += ' AND eu.franchise_user_id = :franchise_id'
        params['franchise_id'] = franchise_id
    elif 'SuperUser' not in roles:
        fid = _require_franchise(db, current_user)
        where_manager += ' AND mu.franchise_user_id = :franchise_id'
        where_employee += ' AND eu.franchise_user_id = :franchise_id'
        params['franchise_id'] = fid
    rows = []
    managers = db.execute(text(f"""
        SELECT 'Manager' AS staff_type, mu.id AS staff_id, mu.user_id, mu.franchise_user_id, mu.id_number,
               'Manager' AS role_label, mu.name, mu.surname, mu.email, mu.contact_number, mu.id_number,
               mu.office_address_assigned, a.name AS office_name,
               COALESCE(mu.profile_photo, u.profile_photo) AS profile_photo,
               COALESCE(mu.profile_photo_mime, u.profile_photo_mime) AS profile_photo_mime,
               fu.franchise_name, fu.business_name, fu.website, fu.office_address
        FROM manager_users mu
        JOIN users u ON u.id = mu.user_id
        LEFT JOIN franchise_users fu ON fu.id = mu.franchise_user_id
        LEFT JOIN gps_allocations_per_user g ON g.user_id = mu.user_id AND COALESCE(g.is_active, TRUE) = TRUE
        LEFT JOIN areas a ON a.id = g.area_id
        WHERE {where_manager}
    """), params).mappings().all()
    employees = db.execute(text(f"""
        SELECT 'Employee' AS staff_type, eu.id AS staff_id, eu.user_id, eu.franchise_user_id, eu.id_number,
               COALESCE(eu.employee_role, 'Employee') AS role_label, eu.id_number, eu.name, eu.surname, eu.email, eu.contact_number,
               eu.office_address_assigned, a.name AS office_name,
               COALESCE(eu.profile_photo, u.profile_photo) AS profile_photo,
               COALESCE(eu.profile_photo_mime, u.profile_photo_mime) AS profile_photo_mime,
               fu.franchise_name, fu.business_name, fu.website, fu.office_address
        FROM employee_users eu
        JOIN users u ON u.id = eu.user_id
        LEFT JOIN franchise_users fu ON fu.id = eu.franchise_user_id
        LEFT JOIN gps_allocations_per_user g ON g.user_id = eu.user_id AND COALESCE(g.is_active, TRUE) = TRUE
        LEFT JOIN areas a ON a.id = g.area_id
        WHERE {where_employee}
    """), params).mappings().all()
    for r in list(managers) + list(employees):
        rows.append(dict(r))
    return sorted(rows, key=lambda x: ((x.get('franchise_name') or x.get('business_name') or ''), (x.get('name') or ''), (x.get('surname') or '')))


def _logo_flowable(width_mm=16, height_mm=10):
    try:
        from reportlab.lib.units import mm
        from reportlab.platypus import Image
        logo_path = Path(__file__).resolve().parents[1] / 'static' / 'logo.png'
        if not logo_path.exists():
            return None
        return Image(str(logo_path), width=width_mm*mm, height=height_mm*mm, kind='proportional')
    except Exception:
        return None


ID_CARD_LAYOUT = {
    "purple": "#6d28d9",
    "text": "#1f1630",
    "muted": "#6b6478",
    "line": "#eee6fb",
    "issued": "21 May 2025",
    "validity": "No Expiry",
}


def _id_card_values(row: dict) -> dict:
    website = (row.get("website") or "").strip()
    if website and not website.lower().startswith(("http://", "https://")):
        website = "https://" + website
    return {
        "first_name": str(row.get("name") or "").strip() or f"User #{row.get('user_id')}",
        "surname": str(row.get("surname") or "").strip(),
        "role_label": str(row.get("role_label") or row.get("employee_role") or row.get("staff_type") or "Staff").strip(),
        "franchise_name": str(row.get("franchise_name") or row.get("business_name") or "Franchise").strip(),
        "user_id": row.get("user_id") or row.get("staff_id") or "",
        "qr_payload": website or "https://martinsdirect.co.za",
    }


def _build_id_cards_pdf(staff_rows: list[dict], current_user: User) -> bytes:
    """Build staff ID cards to mirror the shared .staff-id-card CSS layout."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from xml.sax.saxutils import escape
    except ImportError:
        raise HTTPException(status_code=500, detail='ID card PDF export requires reportlab. Run: pip install -r requirements.txt')

    purple = colors.HexColor('#6d28d9')
    text_color = colors.HexColor('#000000')
    muted = colors.HexColor('#060606')
    white = colors.white

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=8*mm,
        rightMargin=8*mm,
        topMargin=8*mm,
        bottomMargin=8*mm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='PdfStaffTitle', parent=styles['Normal'], fontSize=11.5, leading=11.5, textColor=purple, spaceAfter=0))
    styles.add(ParagraphStyle(name='PdfStaffSub', parent=styles['Normal'], fontSize=4.8, leading=5.2, textColor=purple, spaceAfter=0))
    styles.add(ParagraphStyle(name='PdfStaffName', parent=styles['Normal'], fontSize=9.8, leading=10.4, textColor=text_color, spaceAfter=0))
    styles.add(ParagraphStyle(name='PdfStaffRole', parent=styles['Normal'], fontSize=5.6, leading=5.8, textColor=white, alignment=1, spaceAfter=0))
    styles.add(ParagraphStyle(name='PdfStaffFranchise', parent=styles['Normal'], fontSize=5.8, leading=6.3, textColor=muted, spaceAfter=0))
    styles.add(ParagraphStyle(name='PdfStaffMetaLabel', parent=styles['Normal'], fontSize=4.8, leading=5.0, textColor=muted, alignment=1, spaceAfter=0))
    styles.add(ParagraphStyle(name='PdfStaffMetaValue', parent=styles['Normal'], fontSize=4.9, leading=5.1, textColor=muted, alignment=1, spaceAfter=0))
    styles.add(ParagraphStyle(name='PdfStaffMetaActive', parent=styles['Normal'], fontSize=4.9, leading=5.1, textColor=colors.HexColor('#15803d'), alignment=1, spaceAfter=0))
    styles.add(ParagraphStyle(name='PdfStaffFooter', parent=styles['Normal'], fontSize=6.0, leading=6.2, textColor=white, alignment=1, spaceAfter=0))
    styles.add(ParagraphStyle(name='PdfStaffTiny', parent=styles['Normal'], fontSize=5, leading=5.2, textColor=muted, alignment=1))
    styles.add(ParagraphStyle(name='PdfPageSmall', parent=styles['Normal'], fontSize=7, leading=8))

    story = [
        Paragraph('Staff ID Cards', styles['Title']),
        Paragraph(f'Generated by {escape(current_user.full_name or current_user.email or "System Administrator")}', styles['PdfPageSmall']),
        Spacer(1, 4*mm),
    ]

    card_w = 84 * mm
    card_h = 54 * mm
    safe = 3 * mm
    inner_w = 78 * mm
    header_h = 9.5 * mm
    main_h = 26.0 * mm
    meta_h = 8.0 * mm
    footer_h = 4.5 * mm

    def _fit_text(value, limit=32):
        value = str(value or '').strip()
        return value if len(value) <= limit else value[:limit-1] + '...'

    def _staff_qr_target_for_pdf(row):
        website = (row.get('website') or '').strip()
        if website:
            if not website.lower().startswith(('http://', 'https://')):
                website = 'https://' + website
            return website
        return 'https://martinsdirect.co.za'

    def _meta_cell(label, value, active=False):
        value_style = styles['PdfStaffMetaActive'] if active else styles['PdfStaffMetaValue']
        return [
            Paragraph(f'<b>{escape(str(label))}</b>', styles['PdfStaffMetaLabel']),
            Paragraph(escape(str(value)), value_style),
        ]

    def card(row):
        first_name = str(row.get('name') or '').strip() or f"User #{row.get('user_id')}"
        surname = str(row.get('surname') or '').strip()
        role_label = str(row.get('role_label') or row.get('staff_type') or 'Staff')
        franchise_name = row.get('franchise_name') or row.get('business_name') or 'Franchise'
        user_id = row.get('user_id') or row.get('staff_id') or ''
        qr_payload = _staff_qr_target_for_pdf(row)

        logo = _logo_flowable(123, 13.5) or Paragraph('<b>LOGO</b>', styles['PdfStaffTiny'])
        title_block = Table([
            [Paragraph('<b>STAFF ID</b>', styles['PdfStaffTitle'])],
            [Paragraph('Attendance Register Platform', styles['PdfStaffSub'])],
        ], colWidths=[46*mm], rowHeights=[5.5*mm, 4.0*mm])
        title_block.setStyle(TableStyle([
            ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        header = Table([[title_block, logo]], colWidths=[48*mm, 30*mm], rowHeights=[header_h])
        header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,0), 'RIGHT'),
            ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))

        photo = _photo_flowable(row.get('profile_photo'), width_mm=18, height_mm=23)
        if photo is None:
            photo = Paragraph('<b>ID</b><br/><font size="4">PHOTO</font>', styles['PdfStaffTiny'])
        photo_box = Table([[photo]], colWidths=[18*mm], rowHeights=[23*mm])
        photo_box.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f2edf9')),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))

        role_badge = Table([[Paragraph(f'<b>{escape(_fit_text(role_label, 22))}</b>', styles['PdfStaffRole'])]], colWidths=[38*mm], rowHeights=[5.6*mm])
        role_badge.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), purple), ('BOX', (0,0), (-1,-1), 0, purple),
            ('LEFTPADDING', (0,0), (-1,-1), 1.5), ('RIGHTPADDING', (0,0), (-1,-1), 1.5),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        info = Table([
            [Paragraph(f'<b>{escape(_fit_text(first_name, 20))}</b>', styles['PdfStaffName'])],
            [Paragraph(f'<b>{escape(_fit_text(surname, 20))}</b>', styles['PdfStaffName']) if surname else Paragraph('', styles['PdfStaffName'])],
            [role_badge],
            [Paragraph(f'Franchise: {escape(_fit_text(str(franchise_name), 32))}', styles['PdfStaffFranchise'])],
        ], colWidths=[38*mm], rowHeights=[5.2*mm, 5.2*mm, 6.3*mm, 6.0*mm])
        info.setStyle(TableStyle([
            ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))

        qr_drawing = _id_qr_drawing(qr_payload, 18)
        qr_box = Table([[qr_drawing]], colWidths=[18*mm], rowHeights=[18*mm])
        qr_box.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 0.8, purple), ('BACKGROUND', (0,0), (-1,-1), white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        qr_holder = Table([[qr_box]], colWidths=[18*mm], rowHeights=[18*mm])
        qr_holder.setStyle(TableStyle([
            ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('ALIGN', (0,0), (-1,-1), 'RIGHT'), 
            ('VALIGN', (2,0), (2,0), 'TOP'),
            
        ]))

        main = Table([[photo_box, info, qr_holder]], colWidths=[20*mm, 40*mm, 18*mm], rowHeights=[main_h])
        main.setStyle(TableStyle([
            ('VALIGN', (1,0), (0,0), 'MIDDLE'), ('VALIGN', (-1,0), (-1,0), 'TOP'), ('VALIGN', (2,0), (2,0), 'BOTTOM'),
            ('ALIGN', (0,0), (0,0), 'LEFT'), ('ALIGN', (2,0), (2,0), 'RIGHT'),
            ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))

        meta = Table([[
            _meta_cell('Status', 'Active', active=True),
            _meta_cell('User ID', user_id),
            _meta_cell('Issued', ID_CARD_LAYOUT['issued']),
            _meta_cell('ID Validity', ID_CARD_LAYOUT['validity']),
        ]], colWidths=[19.5*mm, 19.5*mm, 19.5*mm, 19.5*mm], rowHeights=[meta_h])
        meta.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,0), 0.35, white),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))

        footer = Table([[Paragraph(f'Scan QR code or visit {escape(_fit_text(qr_payload, 58))}', styles['PdfStaffFooter'])]], colWidths=[inner_w], rowHeights=[footer_h])
        footer.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), purple), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('LEFTPADDING', (0,0), (-1,-1), 1),
            ('RIGHTPADDING', (0,0), (-1,-1), 1), ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))

        inner = Table([[header], [main], [meta], [footer]], colWidths=[inner_w], rowHeights=[header_h, main_h, meta_h, footer_h])
        inner.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), white), ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0), ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))

        outer = Table([[inner]], colWidths=[card_w], rowHeights=[card_h])
        outer.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1.2, purple), ('BACKGROUND', (0,0), (-1,-1), white),
            ('LEFTPADDING', (0,0), (-1,-1), safe), ('RIGHTPADDING', (0,0), (-1,-1), safe),
            ('TOPPADDING', (0,0), (-1,-1), safe), ('BOTTOMPADDING', (0,0), (-1,-1), safe),
        ]))
        return outer

    grid_rows = []
    current = []
    for row in staff_rows:
        current.append(card(row))
        if len(current) == 2:
            grid_rows.append(current)
            current = []
    if current:
        current.append('')
        grid_rows.append(current)

    grid = Table(grid_rows, colWidths=[84*mm, 84*mm], rowHeights=[54*mm] * len(grid_rows), hAlign='CENTER')
    grid.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))

    story.append(grid)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

@router.get("/offices")
def list_offices(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    names = _roles(db, current_user)
    if "FranchiseUser" not in names and "SuperUser" not in names and "ManagerUser" not in names:
        raise HTTPException(status_code=403, detail="Access denied")
    rows = db.execute(text("""
        SELECT id, name, code, description, latitude, longitude, allowed_radius_m
        FROM areas
        ORDER BY name ASC
    """)).mappings().all()
    return [dict(row) for row in rows]

@router.get("/employee-roles")
def employee_roles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    names = _roles(db, current_user)
    if "FranchiseUser" not in names and "SuperUser" not in names:
        raise HTTPException(status_code=403, detail="Access denied")
    return {"roles": EMPLOYEE_ROLES}


@router.get("/managers")
def list_managers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_office_hours_columns(db)
    _ensure_profile_photo_columns(db)
    if _is_superuser(db, current_user):
        rows = db.execute(text("""
            SELECT
                mu.id,
                mu.user_id,
                mu.franchise_user_id,
                mu.employee_number,
                mu.name,
                mu.surname,
                mu.email AS email,
                mu.contact_number,
                mu.office_address_assigned,
                COALESCE(mu.work_start_time, '08:00') AS work_start_time,
                COALESCE(mu.work_end_time, '17:00') AS work_end_time,
                g.area_id AS office_area_id,
                a.name AS office_name,
                COALESCE(mu.is_active, TRUE) AS is_active,
                u.is_active AS login_active,
                u.username AS username,
                COALESCE(mu.profile_photo, u.profile_photo) AS profile_photo,
                COALESCE(mu.profile_photo_mime, u.profile_photo_mime, 'image/png') AS profile_photo_mime
            FROM manager_users mu
            JOIN users u ON u.id = mu.user_id
            LEFT JOIN gps_allocations_per_user g ON g.user_id = mu.user_id AND COALESCE(g.is_active, TRUE) = TRUE
            LEFT JOIN areas a ON a.id = g.area_id
            WHERE COALESCE(mu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
            ORDER BY mu.id DESC
        """)).mappings().all()
    else:
        franchise_user_id = _require_franchise(db, current_user)
        rows = db.execute(text("""
            SELECT
                mu.id,
                mu.user_id,
                mu.franchise_user_id,
                mu.name,
                mu.surname,
                mu.employee_number,
                mu.email AS email,
                mu.contact_number,
                mu.office_address_assigned,
                COALESCE(mu.work_start_time, '08:00') AS work_start_time,
                COALESCE(mu.work_end_time, '17:00') AS work_end_time,
                g.area_id AS office_area_id,
                a.name AS office_name,
                COALESCE(mu.is_active, TRUE) AS is_active,
                u.is_active AS login_active,
                u.username AS username,
                COALESCE(mu.profile_photo, u.profile_photo) AS profile_photo,
                COALESCE(mu.profile_photo_mime, u.profile_photo_mime, 'image/png') AS profile_photo_mime
            FROM manager_users mu
            JOIN users u ON u.id = mu.user_id
            LEFT JOIN gps_allocations_per_user g ON g.user_id = mu.user_id AND COALESCE(g.is_active, TRUE) = TRUE
            LEFT JOIN areas a ON a.id = g.area_id
            WHERE mu.franchise_user_id = :franchise_user_id
              AND COALESCE(mu.is_active, TRUE) = TRUE
              AND COALESCE(u.is_active, TRUE) = TRUE
            ORDER BY mu.id DESC
        """), {"franchise_user_id": franchise_user_id}).mappings().all()

    return [_public_staff_dict(row) for row in rows]

def _ensure_office_hours_columns(db: Session):
    try:
        db.execute(text("""
            ALTER TABLE manager_users
            ADD COLUMN IF NOT EXISTS work_start_time VARCHAR(5) DEFAULT '08:00'
        """))
        db.execute(text("""
            ALTER TABLE manager_users
            ADD COLUMN IF NOT EXISTS employee_number VARCHAR(50) NULL
        """))
        db.execute(text("""
            ALTER TABLE manager_users
            ADD COLUMN IF NOT EXISTS work_end_time VARCHAR(5) DEFAULT '17:00'
        """))
        db.execute(text("""
            ALTER TABLE employee_users
            ADD COLUMN IF NOT EXISTS employee_number VARCHAR(50) NULL
        """))
        db.execute(text("""
            ALTER TABLE employee_users
            ADD COLUMN IF NOT EXISTS work_start_time VARCHAR(5) DEFAULT '08:00'
        """))
        db.execute(text("""
            ALTER TABLE employee_users
            ADD COLUMN IF NOT EXISTS work_end_time VARCHAR(5) DEFAULT '17:00'
        """))
        db.commit()
    except Exception:
        db.rollback()
        raise
    
@router.get("/employees")
def list_employees(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_office_hours_columns(db)
    _ensure_profile_photo_columns(db)
    if _is_superuser(db, current_user):
        rows = db.execute(text("""
            SELECT
                eu.id,
                eu.user_id,
                eu.franchise_user_id,
                eu.manager_user_id,
                eu.employee_role,
                eu.employee_number,
                eu.name,
                eu.surname,
                eu.email AS email,
                eu.contact_number,
                eu.office_address_assigned,
                COALESCE(eu.work_start_time, '08:00') AS work_start_time,
                COALESCE(eu.work_end_time, '17:00') AS work_end_time,
                g.area_id AS office_area_id,
                a.name AS office_name,
                COALESCE(eu.is_active, TRUE) AS is_active,
                u.is_active AS login_active,
                u.username AS username,
                COALESCE(eu.profile_photo, u.profile_photo) AS profile_photo,
                COALESCE(eu.profile_photo_mime, u.profile_photo_mime, 'image/png') AS profile_photo_mime
            FROM employee_users eu
            JOIN users u ON u.id = eu.user_id
            LEFT JOIN gps_allocations_per_user g ON g.user_id = eu.user_id AND COALESCE(g.is_active, TRUE) = TRUE
            LEFT JOIN areas a ON a.id = g.area_id
            WHERE COALESCE(eu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
            ORDER BY eu.id DESC
        """)).mappings().all()
    else:
        franchise_user_id = _require_franchise(db, current_user)
        rows = db.execute(text("""
            SELECT
                eu.id,
                eu.user_id,
                eu.franchise_user_id,
                eu.manager_user_id,
                eu.employee_role,
                eu.employee_number,
                eu.name,
                eu.surname,
                eu.email AS email,
                eu.contact_number,
                eu.office_address_assigned,
                COALESCE(eu.work_start_time, '08:00') AS work_start_time,
                COALESCE(eu.work_end_time, '17:00') AS work_end_time,
                g.area_id AS office_area_id,
                a.name AS office_name,
                COALESCE(eu.is_active, TRUE) AS is_active,
                u.is_active AS login_active,
                u.username AS username,
                COALESCE(eu.profile_photo, u.profile_photo) AS profile_photo,
                COALESCE(eu.profile_photo_mime, u.profile_photo_mime, 'image/png') AS profile_photo_mime
            FROM employee_users eu
            JOIN users u ON u.id = eu.user_id
            LEFT JOIN gps_allocations_per_user g ON g.user_id = eu.user_id AND COALESCE(g.is_active, TRUE) = TRUE
            LEFT JOIN areas a ON a.id = g.area_id
            WHERE eu.franchise_user_id = :franchise_user_id
              AND COALESCE(eu.is_active, TRUE) = TRUE
              AND COALESCE(u.is_active, TRUE) = TRUE
            ORDER BY eu.id DESC
        """), {"franchise_user_id": franchise_user_id}).mappings().all()

    return [_public_staff_dict(row) for row in rows]

def _create_user(db: Session, full_name: str, email: str | None, password: str, role_name: str, username: str | None = None):
    from app.models.core import User, Role, UserRole
    from app.core.security import hash_password

    login_value = (email or username or "").strip()
    if not login_value:
        raise HTTPException(status_code=400, detail="Email or username is required")

    # Deleted staff records are kept inactive for audit/foreign-key safety, but their
    # old login must not block creating a new staff member with the same email/login.
    # When an inactive user has the requested login, move that old login aside and
    # then create the new active account normally. Active accounts still remain protected.
    existing = db.query(User).filter(User.email == login_value).first()
    if existing:
        if getattr(existing, "is_active", True):
            raise HTTPException(status_code=400, detail="Login already exists")
        archived_suffix = f"deleted_{existing.id}_{int(datetime.utcnow().timestamp())}"
        existing.email = f"{archived_suffix}_{existing.email or 'user'}"[:250]
        if getattr(existing, "username", None):
            existing.username = f"{archived_suffix}_{existing.username}"[:100]
        db.flush()

    user = User(
        full_name=full_name,
        email=login_value,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()

    role = db.query(Role).filter(Role.name == role_name).first()
    if role:
        db.add(UserRole(user_id=user.id, role_id=role.id))

    db.flush()
    return user.id

def _valid_hhmm(value, fallback="08:00"):
    value = (value or fallback or "08:00").strip()

    try:
        parts = value.split(":")
        if len(parts) != 2:
            return fallback

        hour = int(parts[0])
        minute = int(parts[1])

        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return fallback

        return f"{hour:02d}:{minute:02d}"
    except Exception:
        return fallback

@router.post("/managers")
def create_manager(payload: CreateManagerRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_office_hours_columns(db)
    franchise_user_id = _require_franchise(db, current_user)
    full_name = f"{payload.name} {payload.surname}".strip()
    login_email = str(payload.email) if payload.email else _safe_email("manager", payload.name, payload.surname)
    login_username = _unique_username(db, payload.username or _safe_username("manager", payload.name, payload.surname))
    user_id = _create_user(db, full_name, login_email, payload.password or "Temp123!", "ManagerUser", login_username)

    manager_id = db.execute(text("""
        INSERT INTO manager_users (
            user_id,
            franchise_user_id,
            employee_number,
            id_number,
            name,
            surname,
            email,
            contact_number,
            office_address_assigned,
            work_start_time,
            work_end_time,
            is_active,
            created_at,
            updated_at
        )
        VALUES (
            :user_id,
            :franchise_user_id,
            :employee_number,
            :id_number,
            :name,
            :surname,
            :email,
            :contact_number,
            :office_address_assigned,
            :work_start_time,
            :work_end_time,
            TRUE,
            :now,
            :now
        )
        RETURNING id
    """), {
        "user_id": user_id,
        "franchise_user_id": franchise_user_id,
        "employee_number": payload.employee_number,
        "id_number": payload.id_number,
        "name": payload.name,
        "surname": payload.surname,
        "email": str(payload.email) if payload.email else None,
        "contact_number": payload.contact_number,
        "office_address_assigned": payload.office_address_assigned,
        "work_start_time": _valid_hhmm(payload.work_start_time, "08:00"),
        "work_end_time": _valid_hhmm(payload.work_end_time, "17:00"),
        "now": datetime.utcnow(),
    }).scalar_one()

    _assign_office_gps(db, user_id, payload.office_area_id)
    write_audit_log(db, actor_user_id=current_user.id, action="create", entity_type="manager", entity_id=manager_id, franchise_user_id=franchise_user_id, new_values=payload.model_dump(exclude={"password"}), note="Manager created")
    db.commit()
    return {"message": "Manager created", "manager_id": manager_id, "user_id": user_id, "username": login_username, "login_name": login_username if not payload.email else login_email}



def _valid_hhmm(value, fallback="08:00"):
    value = (value or fallback or "08:00").strip()

    try:
        parts = value.split(":")
        if len(parts) != 2:
            return fallback

        hour = int(parts[0])
        minute = int(parts[1])

        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return fallback

        return f"{hour:02d}:{minute:02d}"
    except Exception:
        return fallback

@router.post("/employees")
def create_employee(payload: CreateEmployeeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_office_hours_columns(db)
    franchise_user_id = _require_franchise(db, current_user)

    if payload.employee_role not in EMPLOYEE_ROLES:
        raise HTTPException(status_code=400, detail="Invalid employee role")

    if payload.manager_user_id:
        manager = db.execute(text("""
            SELECT id
            FROM manager_users
            WHERE id = :manager_user_id
            AND franchise_user_id = :franchise_user_id
        """), {
            "manager_user_id": payload.manager_user_id,
            "franchise_user_id": franchise_user_id,
        }).mappings().first()
        if not manager:
            raise HTTPException(status_code=400, detail="Selected manager is not under your franchise")

    full_name = f"{payload.name} {payload.surname}".strip()
    login_email = str(payload.email) if payload.email else _safe_email("employee", payload.name, payload.surname)
    login_username = _unique_username(db, payload.username or _safe_username("employee", payload.name, payload.surname))
    
    employee_id = db.execute(text("""
        INSERT INTO employee_users (
            user_id,
            franchise_user_id,
            manager_user_id,
            employee_role,
            employee_number,
            id_number,
            name,
            surname,
            email,
            contact_number,
            office_address_assigned,
            work_start_time,
            work_end_time,
            is_active,
            created_at,
            updated_at
        )
        VALUES (
            :user_id,
            :franchise_user_id,
            :manager_user_id,
            :employee_role,
            :employee_number,
            :id_number,
            :name,
            :surname,
            :email,
            :contact_number,
            :office_address_assigned,
            :work_start_time,
            :work_end_time,
            TRUE,
            :now,
            :now
        )
        RETURNING id
    """), {
        "user_id": user_id,
        "franchise_user_id": franchise_user_id,
        "manager_user_id": payload.manager_user_id,
        "employee_role": payload.employee_role,
        "employee_number": payload.employee_number,
        "id_number": payload.id_number,
        "name": payload.name,
        "surname": payload.surname,
        "email": str(payload.email) if payload.email else None,
        "contact_number": payload.contact_number,
        "office_address_assigned": payload.office_address_assigned,
        "work_start_time": _valid_hhmm(payload.work_start_time, "08:00"),
        "work_end_time": _valid_hhmm(payload.work_end_time, "17:00"),
        "now": datetime.utcnow(),
    }).scalar_one()

    _assign_office_gps(db, user_id, payload.office_area_id)
    write_audit_log(db, actor_user_id=current_user.id, action="create", entity_type="employee", entity_id=employee_id, franchise_user_id=franchise_user_id, new_values=payload.model_dump(exclude={"password"}), note="Employee created")
    db.commit()
    return {"message": "Employee created", "employee_id": employee_id, "user_id": user_id, "username": login_username, "login_name": login_username if not payload.email else login_email}


def _staff_scope_filter(db: Session, current_user: User, table: str, staff_id: int):
    if table not in {"manager_users", "employee_users"}:
        raise HTTPException(status_code=400, detail="Invalid staff type")
    if _is_superuser(db, current_user):
        row = db.execute(text(f"""
            SELECT s.*, u.email AS login_email, u.full_name AS login_full_name, u.is_active AS login_active,
                   COALESCE(s.profile_photo, u.profile_photo) AS profile_photo,
                   COALESCE(s.profile_photo_mime, u.profile_photo_mime, 'image/png') AS profile_photo_mime
            FROM {table} s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = :staff_id
        """), {"staff_id": staff_id}).mappings().first()
    else:
        franchise_user_id = _require_franchise(db, current_user)
        row = db.execute(text(f"""
            SELECT s.*, u.email AS login_email, u.full_name AS login_full_name, u.is_active AS login_active,
                   COALESCE(s.profile_photo, u.profile_photo) AS profile_photo,
                   COALESCE(s.profile_photo_mime, u.profile_photo_mime, 'image/png') AS profile_photo_mime
            FROM {table} s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = :staff_id AND s.franchise_user_id = :franchise_user_id
        """), {"staff_id": staff_id, "franchise_user_id": franchise_user_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Staff member not found in your scope")
    return row


def _staff_detail(db: Session, table: str, staff_id: int, current_user: User):
    row = _staff_scope_filter(db, current_user, table, staff_id)

    gps = db.execute(text("""
        SELECT g.area_id, a.name AS office_name, a.latitude, a.longitude,
               COALESCE(a.allowed_radius_m, g.radius_meters) AS allowed_radius_m
        FROM gps_allocations_per_user g
        LEFT JOIN areas a ON a.id = g.area_id
        WHERE g.user_id = :user_id AND COALESCE(g.is_active, TRUE) = TRUE
        ORDER BY g.id DESC
        LIMIT 1
    """), {"user_id": row["user_id"]}).mappings().first()

    data = dict(row)

    if gps:
        data.update(dict(gps))

    try:
        docs = db.execute(text("""
            SELECT id, original_filename, content_type, file_size, tax_year, notes, created_at, uploaded_by_user_id
            FROM irp5_documents
            WHERE target_user_id = :target_user_id AND COALESCE(is_active, TRUE) = TRUE
            ORDER BY created_at DESC
        """), {"target_user_id": row["user_id"]}).mappings().all()
        data["documents"] = [dict(d) for d in docs]
    except Exception:
        data["documents"] = []

    franchise = db.execute(text("""
        SELECT franchise_name, business_name, website, office_address
        FROM franchise_users
        WHERE id = :fid
        LIMIT 1
    """), {"fid": row["franchise_user_id"]}).mappings().first()

    if franchise:
        data["franchise_name"] = franchise["franchise_name"] or franchise["business_name"]
        data["business_name"] = franchise["business_name"]
        data["website"] = franchise["website"]
        data["office_address"] = franchise["office_address"]

    qr_payload = _staff_qr_target(
        db,
        data.get("franchise_user_id"),
        data.get("office_address_assigned") or data.get("office_address")
    )

    data["qr_payload"] = qr_payload
    data["qr_image_url"] = _qr_png_data_url(qr_payload)
    data["status"] = "Active" if data.get("is_active", True) else "Inactive"

    return _public_staff_dict(data)

@router.get("/managers/{manager_id}")
def get_manager(manager_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_office_hours_columns(db)
    return _staff_detail(db, "manager_users", manager_id, current_user)


@router.get("/employees/{employee_id}")
def get_employee(employee_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_office_hours_columns(db)
    return _staff_detail(db, "employee_users", employee_id, current_user)


@router.put("/managers/{manager_id}")
def update_manager(manager_id: int, payload: UpdateManagerRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_office_hours_columns(db)
    row = _staff_scope_filter(db, current_user, "manager_users", manager_id)
    values = payload.model_dump(exclude_unset=True)
    if 'work_start_time' in values:
        values['work_start_time'] = _valid_hhmm(values.get('work_start_time'), '08:00')
    if 'work_end_time' in values:
        values['work_end_time'] = _valid_hhmm(values.get('work_end_time'), '17:00')
    updates = []
    params = {"manager_id": manager_id, "now": datetime.utcnow()}
    for field in ["employee_number", "id_number", "name", "surname", "email", "contact_number", "office_address_assigned", "work_start_time", "work_end_time", "is_active"]:
        if field in values:
            updates.append(f"{field} = :{field}")
            params[field] = str(values[field]) if field == "email" and values[field] else values[field]
    if updates:
        updates.append("updated_at = :now")
        db.execute(text(f"UPDATE manager_users SET {', '.join(updates)} WHERE id = :manager_id"), params)
    if "name" in values or "surname" in values or "email" in values or "username" in values or "is_active" in values or "password" in values:
        user_updates = ["updated_at = :now"]
        user_params = {"user_id": row["user_id"], "now": params["now"]}
        full_name = f"{values.get('name', row['name'])} {values.get('surname', row['surname'])}".strip()
        user_updates.append("full_name = :full_name")
        user_params["full_name"] = full_name
        if values.get("email"):
            user_updates.append("email = :email")
            user_params["email"] = str(values["email"])
        if values.get("username"):
            user_updates.append("username = :username")
            user_params["username"] = _unique_username(db, str(values["username"]))
        if "is_active" in values:
            user_updates.append("is_active = :is_active")
            user_params["is_active"] = values["is_active"]
        if values.get("password"):
            user_updates.append("password_hash = :password_hash")
            user_params["password_hash"] = _hash_password(values["password"])
        db.execute(text(f"UPDATE users SET {', '.join(user_updates)} WHERE id = :user_id"), user_params)
    if "office_area_id" in values:
        _assign_office_gps(db, row["user_id"], values.get("office_area_id"))
    write_audit_log(db, actor_user_id=current_user.id, action="update", entity_type="manager", entity_id=manager_id, franchise_user_id=row["franchise_user_id"], old_values=dict(row), new_values=values, note="Manager edited")
    db.commit()
    return {"message": "Manager updated", "manager_id": manager_id}


@router.put("/employees/{employee_id}")
def update_employee(employee_id: int, payload: UpdateEmployeeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_office_hours_columns(db)
    row = _staff_scope_filter(db, current_user, "employee_users", employee_id)
    values = payload.model_dump(exclude_unset=True)
    if 'work_start_time' in values:
        values['work_start_time'] = _valid_hhmm(values.get('work_start_time'), '08:00')
    if 'work_end_time' in values:
        values['work_end_time'] = _valid_hhmm(values.get('work_end_time'), '17:00')
    if values.get("employee_role") and values["employee_role"] not in EMPLOYEE_ROLES:
        raise HTTPException(status_code=400, detail="Invalid employee role")
    if values.get("manager_user_id"):
        manager = db.execute(text("""
            SELECT id FROM manager_users
            WHERE id = :manager_user_id AND franchise_user_id = :franchise_user_id
        """), {"manager_user_id": values["manager_user_id"], "franchise_user_id": row["franchise_user_id"]}).mappings().first()
        if not manager:
            raise HTTPException(status_code=400, detail="Selected manager is not under this franchise")
    updates = []
    params = {"employee_id": employee_id, "now": datetime.utcnow()}
    for field in ["employee_role", "employee_number", "name", "surname", "id_number", "email", "contact_number", "office_address_assigned", "work_start_time", "work_end_time", "manager_user_id", "is_active"]:
        if field in values:
            updates.append(f"{field} = :{field}")
            params[field] = str(values[field]) if field == "email" and values[field] else values[field]
    if updates:
        updates.append("updated_at = :now")
        db.execute(text(f"UPDATE employee_users SET {', '.join(updates)} WHERE id = :employee_id"), params)
    if "name" in values or "surname" in values or "email" in values or "username" in values or "is_active" in values or "password" in values:
        user_updates = ["updated_at = :now"]
        user_params = {"user_id": row["user_id"], "now": params["now"]}
        full_name = f"{values.get('name', row['name'])} {values.get('surname', row['surname'])}".strip()
        user_updates.append("full_name = :full_name")
        user_params["full_name"] = full_name
        if values.get("email"):
            user_updates.append("email = :email")
            user_params["email"] = str(values["email"])
        if values.get("username"):
            user_updates.append("username = :username")
            user_params["username"] = _unique_username(db, str(values["username"]))
        if "is_active" in values:
            user_updates.append("is_active = :is_active")
            user_params["is_active"] = values["is_active"]
        if values.get("password"):
            user_updates.append("password_hash = :password_hash")
            user_params["password_hash"] = _hash_password(values["password"])
        db.execute(text(f"UPDATE users SET {', '.join(user_updates)} WHERE id = :user_id"), user_params)
    if "office_area_id" in values:
        _assign_office_gps(db, row["user_id"], values.get("office_area_id"))
    write_audit_log(db, actor_user_id=current_user.id, action="update", entity_type="employee", entity_id=employee_id, franchise_user_id=row["franchise_user_id"], old_values=dict(row), new_values=values, note="Employee edited")
    db.commit()
    return {"message": "Employee updated", "employee_id": employee_id}


@router.delete("/managers/{manager_id}")
def delete_manager(manager_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _staff_scope_filter(db, current_user, "manager_users", manager_id)
    now = datetime.utcnow()
    related_deleted = _delete_manager_related_records(db, manager_id, row["user_id"])
    db.execute(text("UPDATE manager_users SET is_active = FALSE, updated_at = :now WHERE id = :manager_id"), {"manager_id": manager_id, "now": now})
    db.execute(text("UPDATE users SET is_active = FALSE, updated_at = :now WHERE id = :user_id"), {"user_id": row["user_id"], "now": now})
    write_audit_log(db, actor_user_id=current_user.id, action="deactivate", entity_type="manager", entity_id=manager_id, franchise_user_id=row["franchise_user_id"], old_values=dict(row), new_values={"is_active": False, "related_deleted": related_deleted}, note="Manager deactivated and related overview, history, approvals, leave, payroll and IRP5 data deleted")
    db.commit()
    return {"message": "Manager made inactive", "manager_id": manager_id, "related_deleted": related_deleted}


@router.delete("/employees/{employee_id}")
def delete_employee(employee_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _staff_scope_filter(db, current_user, "employee_users", employee_id)
    now = datetime.utcnow()
    related_deleted = _delete_employee_related_records(db, employee_id, row["user_id"])
    db.execute(text("UPDATE employee_users SET is_active = FALSE, updated_at = :now WHERE id = :employee_id"), {"employee_id": employee_id, "now": now})
    db.execute(text("UPDATE users SET is_active = FALSE, updated_at = :now WHERE id = :user_id"), {"user_id": row["user_id"], "now": now})
    write_audit_log(db, actor_user_id=current_user.id, action="deactivate", entity_type="employee", entity_id=employee_id, franchise_user_id=row["franchise_user_id"], old_values=dict(row), new_values={"is_active": False, "related_deleted": related_deleted}, note="Employee deactivated and related overview, history, approvals, leave, payroll and IRP5 data deleted")
    db.commit()
    return {"message": "Employee made inactive", "employee_id": employee_id, "related_deleted": related_deleted}




@router.post("/managers/{manager_id}/delete")
def delete_manager_post(manager_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return delete_manager(manager_id, current_user, db)


@router.post("/employees/{employee_id}/delete")
def delete_employee_post(employee_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return delete_employee(employee_id, current_user, db)

@router.post("/managers/{manager_id}/reset-password")
def reset_manager_password(manager_id: int, payload: ResetPasswordRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _staff_scope_filter(db, current_user, "manager_users", manager_id)
    now = datetime.utcnow()
    db.execute(text("UPDATE users SET password_hash = :password_hash, updated_at = :now WHERE id = :user_id"), {
        "password_hash": _hash_password(payload.password),
        "user_id": row["user_id"],
        "now": now,
    })
    write_audit_log(db, actor_user_id=current_user.id, action="reset_password", entity_type="manager", entity_id=manager_id, franchise_user_id=row["franchise_user_id"], new_values={"password_reset": True}, note="Manager password reset")
    db.commit()
    return {"message": "Manager password reset", "manager_id": manager_id}


@router.post("/employees/{employee_id}/reset-password")
def reset_employee_password(employee_id: int, payload: ResetPasswordRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _staff_scope_filter(db, current_user, "employee_users", employee_id)
    now = datetime.utcnow()
    db.execute(text("UPDATE users SET password_hash = :password_hash, updated_at = :now WHERE id = :user_id"), {
        "password_hash": _hash_password(payload.password),
        "user_id": row["user_id"],
        "now": now,
    })
    write_audit_log(db, actor_user_id=current_user.id, action="reset_password", entity_type="employee", entity_id=employee_id, franchise_user_id=row["franchise_user_id"], new_values={"password_reset": True}, note="Employee password reset")
    db.commit()
    return {"message": "Employee password reset", "employee_id": employee_id}


@router.post('/{staff_type}/{staff_id}/photo')
def upload_staff_id_photo(staff_type: str, staff_id: int, file: UploadFile = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_profile_photo_columns(db)
    row = _scope_staff_row(db, current_user, staff_type, staff_id)
    if file.content_type not in {'image/jpeg', 'image/png', 'image/webp'}:
        raise HTTPException(status_code=400, detail='Upload a JPG, PNG, or WEBP image')
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail='Empty image upload')
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail='Image is too large. Use 5MB or smaller')
    table = 'employee_users' if staff_type == 'employees' else 'manager_users'
    db.execute(text(f"""
        UPDATE {table}
        SET profile_photo = :photo,
            profile_photo_mime = :mime,
            profile_photo_filename = :filename,
            updated_at = :now
        WHERE id = :staff_id
    """), {'photo': content, 'mime': file.content_type, 'filename': file.filename, 'now': datetime.utcnow(), 'staff_id': staff_id})
    db.execute(text("""
        UPDATE users
        SET profile_photo = :photo,
            profile_photo_mime = :mime,
            profile_photo_filename = :filename,
            updated_at = :now
        WHERE id = :user_id
    """), {'photo': content, 'mime': file.content_type, 'filename': file.filename, 'now': datetime.utcnow(), 'user_id': row['user_id']})
    db.commit()
    return {'success': True, 'message': 'ID photo uploaded', 'user_id': row['user_id']}



@router.get('/id-card/me')
def my_digital_id_card(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_profile_photo_columns(db)
    row = db.execute(text("""
        SELECT 'Employee' AS staff_type, eu.id AS staff_id, eu.user_id, eu.franchise_user_id,
               COALESCE(eu.employee_role, 'Employee') AS role_label, eu.name, eu.surname,
               COALESCE(eu.email, u.email) AS email, eu.contact_number, eu.office_address_assigned,
               a.name AS office_name, COALESCE(eu.profile_photo, u.profile_photo) AS profile_photo,
               COALESCE(eu.profile_photo_mime, u.profile_photo_mime, 'image/png') AS profile_photo_mime,
               fu.franchise_name, fu.business_name, fu.website, fu.office_address
        FROM employee_users eu
        JOIN users u ON u.id = eu.user_id
        LEFT JOIN franchise_users fu ON fu.id = eu.franchise_user_id
        LEFT JOIN gps_allocations_per_user g ON g.user_id = eu.user_id AND COALESCE(g.is_active, TRUE) = TRUE
        LEFT JOIN areas a ON a.id = g.area_id
        WHERE eu.user_id = :uid
        LIMIT 1
    """), {"uid": current_user.id}).mappings().first()
    if not row:
        row = db.execute(text("""
            SELECT 'Manager' AS staff_type, mu.id AS staff_id, mu.user_id, mu.franchise_user_id,
                   'Manager' AS role_label, mu.name, mu.surname, COALESCE(mu.email, u.email) AS email,
                   mu.contact_number, mu.office_address_assigned, a.name AS office_name,
                   COALESCE(mu.profile_photo, u.profile_photo) AS profile_photo,
                   COALESCE(mu.profile_photo_mime, u.profile_photo_mime, 'image/png') AS profile_photo_mime,
                   fu.franchise_name, fu.business_name, fu.website, fu.office_address
            FROM manager_users mu
            JOIN users u ON u.id = mu.user_id
            LEFT JOIN franchise_users fu ON fu.id = mu.franchise_user_id
            LEFT JOIN gps_allocations_per_user g ON g.user_id = mu.user_id AND COALESCE(g.is_active, TRUE) = TRUE
            LEFT JOIN areas a ON a.id = g.area_id
            WHERE mu.user_id = :uid
            LIMIT 1
        """), {"uid": current_user.id}).mappings().first()
    if not row:
        row = db.execute(text("""
            SELECT 'User' AS staff_type, NULL AS staff_id, u.id AS user_id, NULL AS franchise_user_id,
                   'User' AS role_label, COALESCE(u.full_name, u.email) AS name, '' AS surname,
                   u.email, NULL AS contact_number, NULL AS office_address_assigned, NULL AS office_name,
                   u.profile_photo, COALESCE(u.profile_photo_mime, 'image/png') AS profile_photo_mime,
                   NULL AS franchise_name, NULL AS business_name
            FROM users u
            WHERE u.id = :uid
            LIMIT 1
        """), {"uid": current_user.id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail='Digital ID card not found')
    data = dict(row)
    full_name = ' '.join(str(x or '').strip() for x in [data.get('name'), data.get('surname')] if str(x or '').strip()).strip()
    photo_url = None
    photo_bytes = data.get('profile_photo')
    if photo_bytes:
        try:
            mime = data.get('profile_photo_mime') or 'image/png'
            photo_url = f"data:{mime};base64," + base64.b64encode(bytes(photo_bytes)).decode('ascii')
        except Exception:
            photo_url = None
    qr_payload = _staff_qr_target(db, data.get('franchise_user_id'), data.get('office_address_assigned') or data.get('office_address'))
    qr_image_url = _qr_png_data_url(qr_payload)
    return {
        'user_id': data.get('user_id'),
        'staff_id': data.get('staff_id'),
        'staff_type': data.get('staff_type'),
        'full_name': full_name or f"User #{data.get('user_id')}",
        'name': data.get('name') or '',
        'surname': data.get('surname') or '',
        'role_label': data.get('role_label') or data.get('staff_type') or 'Staff',
        'email': data.get('email'),
        'contact_number': data.get('contact_number'),
        'franchise_name': data.get('franchise_name') or data.get('business_name') or 'Franchise',
        'office': data.get('office_name') or data.get('office_address_assigned') or 'Not assigned',
        'photo_url': photo_url,
        'qr_payload': qr_payload,
        'qr_image_url': qr_image_url,
        'status': 'Active',
    }

@router.get('/id-cards/export')
def export_id_cards(
    franchise_id: int | None = Query(default=None),
    staff_type: str | None = Query(default=None),
    staff_id: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_profile_photo_columns(db)
    rows = _id_card_staff_rows(db, current_user, franchise_id=franchise_id, staff_type=staff_type, staff_id=staff_id)
    if staff_id is not None and not rows:
        raise HTTPException(status_code=404, detail='Staff ID card not found in your scope')
    content = _build_id_cards_pdf(rows, current_user)
    stamp = datetime.utcnow().strftime('%Y%m%d')
    filename = f"staff_id_card_{staff_type}_{staff_id}_{stamp}.pdf" if staff_id else f"staff_id_cards_{stamp}.pdf"
    return Response(content=content, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{filename}"'})
