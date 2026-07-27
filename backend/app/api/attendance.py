import base64
import binascii
import csv
import io
import math
import zipfile
import secrets
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from math import radians, sin, cos, sqrt, atan2

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from app.core.config import settings
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.core import (
    Area,
    AttendanceEvent,
    GPSAllocationPerUser,
    GPSRule,
    SignatureBlock,
    TimeRegistrarRule,
    User,
    UserRole,
)
from app.services.notification_service import create_notification
from app.core.timezone import now_sa_naive, format_sa_datetime
from app.schemas.attendance import (
    ApprovalDecisionRequest,
    ApprovalListResponse,
    AttendanceActionRequest,
    AttendanceActionResponse,
    AttendanceHistoryResponse,
    AttendanceSessionsResponse,
    AttendanceStatusResponse,
)

router = APIRouter()

SHIFT_END_HOUR = 17
SHIFT_END_GRACE_MINUTES = 10
ALLOWED_WORK_TYPES = {'office', 'on_road'}
APPROVAL_ROLES = {'SuperUser', 'FranchiseUser', 'ManagerUser'}
SIGN_ROLES = {'EmployeeUser', 'ManagerUser', 'SuperUser'}

class OfficeLocationUpdateRequest(BaseModel):
    latitude: float
    longitude: float
    allowed_radius_m: int = 100

class OfficeQrValidateRequest(BaseModel):
    qr_value: str


class OfficeCreateRequest(BaseModel):
    name: str
    address: str
    allowed_radius_m: int = 100
    latitude: float | None = None
    longitude: float | None = None

class OfficeDetailsUpdateRequest(BaseModel):
    name: str
    address: str
    allowed_radius_m: int = 100

class OfficeReassignRequest(BaseModel):
    new_address: str
    new_area_id: int | None = None


def _ensure_office_qr_schema(db: Session):
    """Request-time, lightweight schema compatibility for office QR attendance."""
    try:
        db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_token VARCHAR(120)"))
        db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_enabled BOOLEAN NOT NULL DEFAULT TRUE"))
        db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_updated_at TIMESTAMP NULL"))
        db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_valid_week VARCHAR(10) NULL"))
        db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS franchise_user_id INTEGER NULL"))
        db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS office_address TEXT NULL"))
        db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE"))
        db.execute(text("ALTER TABLE areas ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP NULL"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_area_id INTEGER NULL"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_office_name VARCHAR(255) NULL"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_token_hash VARCHAR(128) NULL"))
        db.commit()
    except Exception:
        db.rollback()
        raise


def _extract_qr_token(qr_value: str | None) -> str | None:
    if not qr_value:
        return None
    value = str(qr_value).strip()
    if not value:
        return None
    for prefix in ['ARP-OFFICE:', 'OFFICE:', 'office:']:
        if value.startswith(prefix):
            return value.split(':', 1)[1].strip()
    for key in ['office_qr=', 'qr=', 'token=']:
        if key in value:
            token = value.split(key, 1)[1].split('&', 1)[0].split('#', 1)[0].strip()
            return token or None
    return value


def _qr_payload(token: str) -> str:
    return str(token)


def _qr_scan_url(token: str) -> str:
    base = str(getattr(settings, 'FRONTEND_URL', '') or '').strip().rstrip('/')
    payload = _qr_payload(token)
    if not base:
        return payload
    from urllib.parse import quote
    return f"{base}/?tab=attendance&office_qr={quote(payload, safe='')}"


def _token_hash(token: str | None) -> str | None:
    if not token:
        return None
    return hashlib.sha256(str(token).encode('utf-8')).hexdigest()


def _generate_office_code(db: Session, exclude_area_id: int | None = None) -> str:
    """Return an unused reusable four-digit attendance code."""
    for _ in range(9000):
        candidate = str(1000 + secrets.randbelow(9000))
        params = {'candidate': candidate}
        exclude_sql = ''
        if exclude_area_id is not None:
            exclude_sql = 'AND id <> :exclude_area_id'
            params['exclude_area_id'] = int(exclude_area_id)
        exists = db.execute(text(f"""
            SELECT 1
            FROM areas
            WHERE qr_token = :candidate
              AND franchise_user_id IS NOT NULL
              AND COALESCE(is_archived, FALSE) = FALSE
              {exclude_sql}
            LIMIT 1
        """), params).scalar()
        if not exists:
            return candidate
    raise HTTPException(status_code=503, detail='No office attendance code is currently available')


def _office_code_week(now: datetime | None = None) -> tuple[str, datetime]:
    now = now or now_sa_naive()
    iso_year, iso_week, _ = now.isocalendar()
    next_monday = (now + timedelta(days=7 - now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return f'{iso_year}-W{iso_week:02d}', next_monday


def _office_address(row: dict) -> str:
    return row.get('office_address') or row.get('description') or row.get('code') or row.get('name') or ''


def _normalise_address(value: str | None) -> str:
    return ' '.join(str(value or '').strip().lower().split())


def _franchise_scope_for_user(db: Session, user_id: int) -> tuple[int | None, str | None]:
    row = db.execute(text("""
        SELECT fu.id AS franchise_user_id, fu.office_address
        FROM franchise_users fu
        WHERE fu.user_id = :user_id AND COALESCE(fu.is_active, TRUE) = TRUE
        UNION ALL
        SELECT mu.franchise_user_id, fu.office_address
        FROM manager_users mu
        JOIN franchise_users fu ON fu.id = mu.franchise_user_id
        WHERE mu.user_id = :user_id AND COALESCE(mu.is_active, TRUE) = TRUE
        UNION ALL
        SELECT eu.franchise_user_id, fu.office_address
        FROM employee_users eu
        JOIN franchise_users fu ON fu.id = eu.franchise_user_id
        WHERE eu.user_id = :user_id AND COALESCE(eu.is_active, TRUE) = TRUE
        LIMIT 1
    """), {'user_id': user_id}).mappings().first()
    if not row:
        return None, None
    return row.get('franchise_user_id'), row.get('office_address')


def _upsert_address_area(db: Session, franchise_user_id: int, address: str, label: str) -> dict:
    normalized = _normalise_address(address)
    if not normalized:
        raise HTTPException(status_code=400, detail='A complete office address is required')
    address_key = hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:12]
    code = f'F{franchise_user_id}-ADDR-{address_key}'
    row = db.execute(text("""
        SELECT id, name, code, description, office_address, latitude, longitude, allowed_radius_m,
               qr_token, COALESCE(qr_enabled, TRUE) AS qr_enabled, COALESCE(is_archived, FALSE) AS is_archived, archived_at, franchise_user_id
        FROM areas
        WHERE franchise_user_id = :fid AND code = :code
        LIMIT 1
    """), {'fid': franchise_user_id, 'code': code}).mappings().first()
    now = now_sa_naive()
    if row:
        db.execute(text("""
            UPDATE areas
            SET name = :name, description = :address, office_address = :address,
                is_archived = FALSE, archived_at = NULL, qr_enabled = TRUE, updated_at = :now
            WHERE id = :id
        """), {'name': label[:120], 'address': address.strip(), 'now': now, 'id': row['id']})
        area_id = int(row['id'])
    else:
        token = _generate_office_code(db)
        inserted = db.execute(text("""
            INSERT INTO areas (name, code, description, office_address, allowed_radius_m, franchise_user_id,
                               qr_token, qr_enabled, is_archived, qr_updated_at, created_at, updated_at)
            VALUES (:name, :code, :address, :address, 100, :fid, :token, TRUE, FALSE, :now, :now, :now)
            RETURNING id
        """), {'name': label[:120], 'code': code, 'address': address.strip(),
                 'fid': franchise_user_id, 'token': token, 'now': now}).mappings().first()
        area_id = int(inserted['id'])
    db.commit()
    return _office_qr_row(db, area_id)


def _assign_user_to_area(db: Session, user_id: int, area: dict):
    current = db.execute(text("""
        SELECT id, area_id FROM gps_allocations_per_user
        WHERE user_id = :user_id AND COALESCE(is_active, TRUE) = TRUE
        ORDER BY id DESC LIMIT 1
    """), {'user_id': user_id}).mappings().first()
    if current and int(current.get('area_id') or 0) == int(area['id']):
        return
    now = now_sa_naive()
    db.execute(text("UPDATE gps_allocations_per_user SET is_active = FALSE, updated_at = :now WHERE user_id = :user_id"),
               {'now': now, 'user_id': user_id})
    db.execute(text("""
        INSERT INTO gps_allocations_per_user
            (user_id, area_id, latitude, longitude, radius_meters, is_active, created_at, updated_at)
        VALUES (:user_id, :area_id, :latitude, :longitude, :radius, TRUE, :now, :now)
    """), {'user_id': user_id, 'area_id': area['id'], 'latitude': str(area.get('latitude')) if area.get('latitude') is not None else None,
             'longitude': str(area.get('longitude')) if area.get('longitude') is not None else None,
             'radius': area.get('allowed_radius_m') or 100, 'now': now})
    db.commit()


def _sync_franchise_address_areas(db: Session, franchise_user_id: int):
    franchise = db.execute(text("""
        SELECT user_id, COALESCE(business_name, franchise_name, 'Head Office') AS label, office_address
        FROM franchise_users WHERE id = :fid LIMIT 1
    """), {'fid': franchise_user_id}).mappings().first()
    if not franchise:
        return []
    areas_by_address = {}
    if _normalise_address(franchise.get('office_address')):
        area = _upsert_address_area(db, franchise_user_id, franchise['office_address'], franchise.get('label') or 'Business')
        areas_by_address[_normalise_address(franchise['office_address'])] = area
        _assign_user_to_area(db, int(franchise['user_id']), area)
    staff = db.execute(text("""
        SELECT user_id, name, surname, office_address_assigned, 'Manager' AS staff_type
        FROM manager_users
        WHERE franchise_user_id = :fid AND COALESCE(is_active, TRUE) = TRUE
        UNION ALL
        SELECT user_id, name, surname, office_address_assigned, 'Employee' AS staff_type
        FROM employee_users
        WHERE franchise_user_id = :fid AND COALESCE(is_active, TRUE) = TRUE
    """), {'fid': franchise_user_id}).mappings().all()
    for person in staff:
        address = (person.get('office_address_assigned') or franchise.get('office_address') or '').strip()
        if not address:
            continue
        key = _normalise_address(address)
        area = areas_by_address.get(key)
        if not area:
            area = _upsert_address_area(db, franchise_user_id, address, f"Office - {address.split(',')[0].strip()}")
            areas_by_address[key] = area
        _assign_user_to_area(db, int(person['user_id']), area)
    return list(areas_by_address.values())


def _sync_user_address_allocation(db: Session, user_id: int):
    fid, franchise_address = _franchise_scope_for_user(db, user_id)
    if not fid:
        return
    row = db.execute(text("""
        SELECT office_address_assigned FROM manager_users WHERE user_id = :uid
        UNION ALL
        SELECT office_address_assigned FROM employee_users WHERE user_id = :uid
        LIMIT 1
    """), {'uid': user_id}).mappings().first()
    address = ((row.get('office_address_assigned') if row else None) or franchise_address or '').strip()
    if address:
        area = _upsert_address_area(db, int(fid), address, f"Office - {address.split(',')[0].strip()}")
        _assign_user_to_area(db, user_id, area)


def _office_qr_row(db: Session, area_id: int):
    _ensure_office_qr_schema(db)
    row = db.execute(text("""
        SELECT id, name, code, description, office_address, latitude, longitude, allowed_radius_m,
               qr_token, qr_updated_at, qr_valid_week,
               COALESCE(qr_enabled, TRUE) AS qr_enabled,
               COALESCE(is_archived, FALSE) AS is_archived, archived_at, franchise_user_id
        FROM areas
        WHERE id = :area_id
    """), {'area_id': area_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail='Office / area not found')
    row = dict(row)
    token_value = str(row.get('qr_token') or '').strip()
    current_week, valid_until = _office_code_week()
    needs_rotation = (
        len(token_value) != 4
        or not token_value.isdigit()
        or row.get('qr_valid_week') != current_week
    )
    if needs_rotation and not row.get('is_archived'):
        token = _generate_office_code(db, exclude_area_id=area_id)
        db.execute(text("""
            UPDATE areas
            SET qr_token = :token, qr_enabled = TRUE, qr_updated_at = :now,
                qr_valid_week = :valid_week, updated_at = :now
            WHERE id = :area_id
        """), {
            'token': token,
            'now': now_sa_naive(),
            'valid_week': current_week,
            'area_id': area_id,
        })
        db.commit()
        row['qr_token'] = token
        row['qr_enabled'] = True
        row['qr_valid_week'] = current_week
        row['qr_updated_at'] = now_sa_naive()
    row['qr_valid_until'] = valid_until
    return row


def _validate_office_qr_for_user(db: Session, user_id: int, qr_value: str | None):
    """Validate that scanned QR belongs to the user's assigned GPS office/area."""
    _ensure_office_qr_schema(db)
    token = _extract_qr_token(qr_value)
    if not token:
        raise HTTPException(status_code=400, detail='The four-digit office code is required before sign in or out')
    if len(token) != 4 or not token.isdigit():
        raise HTTPException(status_code=400, detail='Enter the four-digit office code')
    _sync_user_address_allocation(db, user_id)
    allocation = db.execute(text("""
        SELECT area_id
        FROM gps_allocations_per_user
        WHERE user_id = :user_id AND COALESCE(is_active, TRUE) = TRUE
        ORDER BY id DESC
        LIMIT 1
    """), {'user_id': user_id}).mappings().first()
    if not allocation or not allocation.get('area_id'):
        raise HTTPException(status_code=400, detail='No active office is assigned to this staff account')
    area = _office_qr_row(db, int(allocation['area_id']))
    if area.get('qr_enabled') is False:
        raise HTTPException(status_code=400, detail='This office attendance code is disabled')
    if token != str(area.get('qr_token') or ''):
        raise HTTPException(status_code=400, detail='Invalid or expired four-digit code for your assigned office')
    return area, token


def _get_last_event(db: Session, user_id: int):
    return (
        db.query(AttendanceEvent)
        .filter(AttendanceEvent.user_id == user_id)
        .order_by(AttendanceEvent.created_at.desc())
        .first()
    )


def _get_role_names(db: Session, user_id: int):
    return [ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user_id).all()]


def _has_any_role(db: Session, user: User, role_names: set[str]):
    return bool(set(_get_role_names(db, user.id)).intersection(role_names))


def _require_employee_access(db: Session, user: User):
    if not _has_any_role(db, user, SIGN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only employee-capable users can sign in or out')


def _require_approval_access(db: Session, user: User):
    if not _has_any_role(db, user, APPROVAL_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only SuperUser, FranchiseUser or ManagerUser can approve attendance')


def _franchise_user_ids(db: Session, franchise_id: int) -> list[int]:
    # Only active logins and active staff profiles may appear in Overview/History.
    # Deleted employees/managers are deactivated, so filtering here prevents old
    # no-attendance rows from being recreated after their attendance records are removed.
    rows = db.execute(text("""
        SELECT fu.user_id
        FROM franchise_users fu
        JOIN users u ON u.id = fu.user_id
        WHERE fu.id = :fid AND COALESCE(fu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
        UNION
        SELECT mu.user_id
        FROM manager_users mu
        JOIN users u ON u.id = mu.user_id
        WHERE mu.franchise_user_id = :fid AND COALESCE(mu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
        UNION
        SELECT eu.user_id
        FROM employee_users eu
        JOIN users u ON u.id = eu.user_id
        WHERE eu.franchise_user_id = :fid AND COALESCE(eu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
    """), {'fid': franchise_id}).mappings().all()
    return sorted({int(r['user_id']) for r in rows if r['user_id'] is not None})


def _visible_attendance_user_ids(db: Session, current_user: User, franchise_id: Optional[int] = None) -> list[int]:
    roles = set(_get_role_names(db, current_user.id))
    if franchise_id is not None:
        if 'SuperUser' in roles:
            return _franchise_user_ids(db, franchise_id)
        own_franchise = None
        if 'FranchiseUser' in roles:
            own_franchise = db.execute(text("""
                SELECT id FROM franchise_users WHERE user_id = :user_id AND COALESCE(is_active, TRUE) = TRUE
            """), {'user_id': current_user.id}).mappings().first()
        elif 'ManagerUser' in roles:
            own_franchise = db.execute(text("""
                SELECT franchise_user_id AS id FROM manager_users WHERE user_id = :user_id AND COALESCE(is_active, TRUE) = TRUE
            """), {'user_id': current_user.id}).mappings().first()
        if own_franchise and int(own_franchise['id']) == int(franchise_id):
            return _franchise_user_ids(db, franchise_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You may only view your own franchise')

    if 'SuperUser' in roles:
        rows = db.execute(text('''
            SELECT DISTINCT u.id
            FROM users u
            LEFT JOIN manager_users mu ON mu.user_id = u.id
            LEFT JOIN employee_users eu ON eu.user_id = u.id
            WHERE COALESCE(u.is_active, TRUE) = TRUE
              AND (
                COALESCE(mu.is_active, TRUE) = TRUE
                OR COALESCE(eu.is_active, TRUE) = TRUE
                OR (mu.id IS NULL AND eu.id IS NULL)
              )
        ''')).mappings().all()
        return [int(r['id']) for r in rows]

    visible = {int(current_user.id)}

    if 'FranchiseUser' in roles:
        franchise = db.execute(text("""
            SELECT id FROM franchise_users
            WHERE user_id = :user_id AND COALESCE(is_active, TRUE) = TRUE
        """), {'user_id': current_user.id}).mappings().first()
        if franchise:
            rows = db.execute(text("""
                SELECT mu.user_id
                FROM manager_users mu
                JOIN users u ON u.id = mu.user_id
                WHERE mu.franchise_user_id = :fid AND COALESCE(mu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
                UNION
                SELECT eu.user_id
                FROM employee_users eu
                JOIN users u ON u.id = eu.user_id
                WHERE eu.franchise_user_id = :fid AND COALESCE(eu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
            """), {'fid': franchise['id']}).mappings().all()
            visible.update(int(r['user_id']) for r in rows if r['user_id'] is not None)

    if 'ManagerUser' in roles:
        manager = db.execute(text("""
            SELECT id, franchise_user_id FROM manager_users
            WHERE user_id = :user_id AND COALESCE(is_active, TRUE) = TRUE
        """), {'user_id': current_user.id}).mappings().first()
        if manager:
            rows = db.execute(text("""
                SELECT eu.user_id
                FROM employee_users eu
                JOIN users u ON u.id = eu.user_id
                WHERE COALESCE(eu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
                  AND eu.manager_user_id = :manager_id
            """), {'manager_id': manager['id']}).mappings().all()
            visible.update(int(r['user_id']) for r in rows if r['user_id'] is not None)

    return sorted(visible)


def _can_view_requested_user(db: Session, current_user: User, requested_user_id: int):
    if requested_user_id in _visible_attendance_user_ids(db, current_user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You may only view attendance for users in your allowed scope')


def _attendance_franchise_recipient(db: Session, staff_user_id: int):
    """Return franchise owner recipient context for the staff user's attendance event."""
    row = db.execute(text("""
        SELECT
            src.franchise_user_id,
            fu.user_id AS recipient_user_id,
            owner.email AS recipient_email,
            COALESCE(owner.full_name, owner.email, 'Franchise user') AS recipient_name,
            src.staff_name,
            src.staff_type,
            COALESCE(fu.franchise_name, owner.full_name, owner.email, 'Franchise') AS franchise_name
        FROM (
            SELECT e.franchise_user_id,
                   COALESCE(NULLIF(TRIM(CONCAT(e.name, ' ', e.surname)), ''), u.full_name, u.email) AS staff_name,
                   'employee' AS staff_type
            FROM employee_users e
            JOIN users u ON u.id = e.user_id
            WHERE e.user_id = :staff_user_id
            UNION ALL
            SELECT m.franchise_user_id,
                   COALESCE(NULLIF(TRIM(CONCAT(m.name, ' ', m.surname)), ''), u.full_name, u.email) AS staff_name,
                   'manager' AS staff_type
            FROM manager_users m
            JOIN users u ON u.id = m.user_id
            WHERE m.user_id = :staff_user_id
            UNION ALL
            SELECT fu.id AS franchise_user_id,
                   COALESCE(u.full_name, u.email) AS staff_name,
                   'franchise' AS staff_type
            FROM franchise_users fu
            JOIN users u ON u.id = fu.user_id
            WHERE fu.user_id = :staff_user_id
        ) src
        JOIN franchise_users fu ON fu.id = src.franchise_user_id
        JOIN users owner ON owner.id = fu.user_id
        WHERE src.franchise_user_id IS NOT NULL
        LIMIT 1
    """), {'staff_user_id': staff_user_id}).mappings().first()
    return dict(row) if row else None


def _notify_franchise_attendance_event(db: Session, event: AttendanceEvent, action_label: str) -> None:
    """Notify the franchise owner and the employee's linked manager."""
    ctx = _attendance_franchise_recipient(db, int(event.user_id))
    if not ctx:
        return
    status_value = event.attendance_status or event.gps_status or 'recorded'
    status_text = _gps_report_label(status_value) if status_value in {'inside_area', 'outside_area', 'accuracy_too_low', 'no_allocation', 'on_road'} else str(status_value).replace('_', ' ').title()
    approval_text = event.approval_status or 'approved'
    signature_text = event.signature_status or ('captured' if getattr(event, 'signature_image', None) else 'missing')
    photo_text = getattr(event, 'photo_status', None) or ('captured' if getattr(event, 'attendance_photo', None) else 'missing')
    when = format_sa_datetime(event.created_at) if event.created_at else format_sa_datetime(now_sa_naive())
    subject = f"Attendance {action_label}: {ctx.get('staff_name')}"
    message = (
        f"{ctx.get('staff_name')} recorded {action_label} on {when}.\n\n"
        f"Franchise: {ctx.get('franchise_name')}\n"
        f"Status: {status_text}\n"
        f"Approval: {approval_text}\n"
        f"Signature: {signature_text}\n"
        f"Automatic photo: {photo_text}\n"
        f"Work type: {event.work_location_type or 'office'}\n\n"
        "Open the Attendance Register Platform to review the event and export the signed PDF if required."
    )
    target_tab = 'approvals' if approval_text == 'pending' else 'history'
    recipients = [{
        'user_id': ctx.get('recipient_user_id'),
        'email': ctx.get('recipient_email'),
    }]
    manager = db.execute(text("""
        SELECT manager_login.id AS recipient_user_id, manager_login.email AS recipient_email
        FROM employee_users employee
        JOIN manager_users manager ON manager.id=employee.manager_user_id
        JOIN users manager_login ON manager_login.id=manager.user_id
        WHERE employee.user_id=:staff_user_id
          AND COALESCE(employee.is_active,TRUE)=TRUE
          AND COALESCE(manager.is_active,TRUE)=TRUE
          AND COALESCE(manager_login.is_active,TRUE)=TRUE
        LIMIT 1
    """), {'staff_user_id':int(event.user_id)}).mappings().first()
    if manager and int(manager['recipient_user_id']) != int(ctx.get('recipient_user_id') or 0):
        recipients.append({'user_id':manager['recipient_user_id'],'email':manager['recipient_email']})
    for recipient in recipients:
        create_notification(
            db,
            notification_type=f'attendance_{event.action}',
            subject=subject,
            message=message,
            recipient_email=recipient.get('email'),
            related_table='attendance_events',
            related_id=int(event.id),
            user_id=int(event.user_id),
            recipient_user_id=recipient.get('user_id'),
            franchise_user_id=ctx.get('franchise_user_id'),
            severity='warning' if approval_text == 'pending' else 'info',
            target_tab=target_tab,
            send_email=True,
        )



def _ensure_attendance_signature_columns(db: Session):
    """Keep older databases compatible with attendance evidence storage."""
    try:
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS signature_image BYTEA"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS signature_image_mime VARCHAR(80)"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS signature_image_filename VARCHAR(255)"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_area_id INTEGER NULL"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_office_name VARCHAR(255) NULL"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_token_hash VARCHAR(128) NULL"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS attendance_photo BYTEA NULL"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS attendance_photo_mime VARCHAR(80) NULL"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS attendance_photo_filename VARCHAR(255) NULL"))
        db.execute(text("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS photo_status VARCHAR(30) NULL"))
        db.commit()
    except Exception:
        db.rollback()
        raise


def _signature_data_url_to_image(signature_value: Optional[str], event_action: str, user_id: int):
    """Convert a canvas data URL into binary image data for DB storage."""
    if not signature_value:
        return None, None, None
    value = str(signature_value).strip()
    if not value.startswith('data:image/') or ';base64,' not in value:
        return None, None, None
    header, encoded = value.split(';base64,', 1)
    mime = header.replace('data:', '').strip().lower() or 'image/png'
    if mime not in {'image/png', 'image/jpeg', 'image/jpg', 'image/webp'}:
        raise HTTPException(status_code=400, detail='Signature image must be PNG, JPG or WEBP')
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail='Signature image data is invalid')
    if not image_bytes:
        raise HTTPException(status_code=400, detail='Signature image is empty')
    if len(image_bytes) > 2_000_000:
        raise HTTPException(status_code=400, detail='Signature image is too large')
    ext = 'jpg' if mime in {'image/jpeg', 'image/jpg'} else mime.split('/')[-1]
    filename = f'signature_user_{int(user_id)}_{event_action}_{now_sa_naive().strftime("%Y%m%d%H%M%S")}.{ext}'
    return image_bytes, mime, filename


def _photo_data_url_to_image(photo_value: Optional[str], event_action: str, user_id: int):
    """Validate and decode the automatically captured attendance photo."""
    if not photo_value:
        raise HTTPException(status_code=400, detail='Automatic attendance photo is required for this action')
    value = str(photo_value).strip()
    if not value.startswith('data:image/') or ';base64,' not in value:
        raise HTTPException(status_code=400, detail='Attendance photo data is invalid')
    header, encoded = value.split(';base64,', 1)
    mime = header.replace('data:', '').strip().lower() or 'image/jpeg'
    if mime not in {'image/png', 'image/jpeg', 'image/jpg', 'image/webp'}:
        raise HTTPException(status_code=400, detail='Attendance photo must be PNG, JPG or WEBP')
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail='Attendance photo data is invalid')
    if not image_bytes:
        raise HTTPException(status_code=400, detail='Attendance photo is empty')
    if len(image_bytes) > 4_000_000:
        raise HTTPException(status_code=400, detail='Attendance photo is too large')
    ext = 'jpg' if mime in {'image/jpeg', 'image/jpg'} else mime.split('/')[-1]
    filename = f'attendance_user_{int(user_id)}_{event_action}_{now_sa_naive().strftime("%Y%m%d%H%M%S")}.{ext}'
    return image_bytes, mime, filename


def _event_signature_bytes(event):
    """Return (bytes, mime) from the new binary column, with data-url fallback."""
    image_bytes = getattr(event, 'signature_image', None)
    mime = getattr(event, 'signature_image_mime', None) or 'image/png'
    if image_bytes:
        return bytes(image_bytes), mime
    value = getattr(event, 'signature_value', None)
    if value and str(value).startswith('data:image/') and ';base64,' in str(value):
        try:
            header, encoded = str(value).split(';base64,', 1)
            return base64.b64decode(encoded), header.replace('data:', '') or 'image/png'
        except Exception:
            return None, None
    return None, None


def _signature_pdf_image(event, width_mm=34, height_mm=12):
    """Build a small ReportLab image flowable for an attendance signature."""
    if not event:
        return None
    image_bytes, _mime = _event_signature_bytes(event)
    if not image_bytes:
        return None
    try:
        from reportlab.lib.units import mm
        from reportlab.platypus import Image
        return Image(io.BytesIO(image_bytes), width=width_mm * mm, height=height_mm * mm, kind='proportional')
    except Exception:
        return None

def _validate_rules(db: Session, user: User, payload: AttendanceActionRequest, is_sign_in: bool):
    _require_employee_access(db, user)

    signature_block = db.query(SignatureBlock).filter(SignatureBlock.user_id == user.id).first()
    if signature_block and signature_block.is_blocked:
        raise HTTPException(status_code=400, detail='Signature is blocked for this user')

    if payload.work_location_type and payload.work_location_type not in ALLOWED_WORK_TYPES:
        raise HTTPException(status_code=400, detail='work_location_type must be office or on_road')

    # Phase 3 requires GPS for every mobile attendance action. A missing rules
    # row must never silently make location optional.
    if payload.latitude is None or payload.longitude is None:
        raise HTTPException(status_code=400, detail='GPS location is required for this action')
    if not (-90 <= float(payload.latitude) <= 90) or not (-180 <= float(payload.longitude) <= 180):
        raise HTTPException(status_code=400, detail='GPS coordinates are invalid')
    accuracy = _payload_accuracy(payload)
    if accuracy is None or float(accuracy) <= 0:
        raise HTTPException(status_code=400, detail='GPS accuracy is required for this action')

    if not payload.signature_value or not str(payload.signature_value).startswith('data:image/'):
        raise HTTPException(status_code=400, detail='Signature is required for this action')
    if not payload.photo_value:
        raise HTTPException(status_code=400, detail='Automatic attendance photo is required for this action')

    if payload.work_location_type == 'on_road' and not payload.employee_note:
        raise HTTPException(status_code=400, detail='Employee note is required when signing on the road')
    if (payload.work_location_type or 'office') == 'office' and not payload.qr_value:
        raise HTTPException(status_code=400, detail='The four-digit office code is required for office attendance')


def _payload_accuracy(payload: AttendanceActionRequest):
    return payload.accuracy_meters if payload.accuracy_meters is not None else payload.accuracy


def haversine(lat1, lon1, lat2, lon2):
    radius_m = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c

def _validate_gps(db: Session, user_id: int, payload: AttendanceActionRequest, office_area_id: int | None = None):
    allocation = (
        db.query(GPSAllocationPerUser)
        .filter(
            GPSAllocationPerUser.user_id == user_id,
            GPSAllocationPerUser.is_active == True,
            *([GPSAllocationPerUser.area_id == office_area_id] if office_area_id is not None else []),
        )
        .order_by(GPSAllocationPerUser.id.desc())
        .first()
    )

    gps_status = 'no_allocation'
    distance = None
    accuracy = _payload_accuracy(payload)

    if allocation and payload.latitude is not None and payload.longitude is not None:
        area = db.query(Area).filter(Area.id == allocation.area_id).first()

        if area and area.latitude is not None and area.longitude is not None:
            distance = haversine(
                float(payload.latitude),
                float(payload.longitude),
                float(area.latitude),
                float(area.longitude),
            )

            allowed_radius = area.allowed_radius_m or allocation.radius_meters or 100

            if (payload.work_location_type or 'office') == 'on_road':
                gps_status = 'on_road'
            elif float(accuracy or 999) > 100:
                gps_status = 'accuracy_too_low'

            elif distance <= allowed_radius:
                gps_status = 'inside_area'

            else:
                gps_status = 'outside_area'

    if (payload.work_location_type or 'office') == 'office' and gps_status == 'no_allocation':
        raise HTTPException(status_code=400, detail='A configured office GPS allocation is required before signing in or out')
    # Range and accuracy exceptions are evidence, not a reason to discard an
    # attendance action. They remain pending for manager/franchise review and
    # are shown in Events/Sessions with the captured coordinates, distance,
    # signature and photo.
    if (payload.work_location_type or 'office') == 'on_road' and gps_status == 'no_allocation':
        gps_status = 'on_road'

    return gps_status, distance


def _approval_defaults(payload: AttendanceActionRequest, gps_status: str):
    work_type = payload.work_location_type or 'office'
    if work_type == 'on_road':
        approval_status = 'pending'
        work_location_type = 'on_road'
    elif gps_status == 'inside_area':
        approval_status = 'pending'
        work_location_type = 'office'
    else:
        approval_status = 'pending'
        work_location_type = 'outside_area'
    signature_status = 'captured' if payload.signature_value else 'missing'
    return approval_status, work_location_type, signature_status


def _gps_report_label(value: str | None) -> str:
    return {
        'inside_area': 'Inside office GPS range',
        'outside_area': 'Not in office GPS range',
        'accuracy_too_low': 'GPS accuracy too low',
        'no_allocation': 'Office GPS allocation missing',
        'on_road': 'On-road attendance',
    }.get(str(value or ''), str(value or 'Not available').replace('_', ' ').title())


def _attendance_action_message(action: str, gps_status: str) -> str:
    label = 'Signed in' if action == 'sign_in' else 'Signed out'
    if gps_status == 'outside_area':
        return f'{label}. Attendance was recorded outside the office GPS range and is pending review.'
    if gps_status == 'accuracy_too_low':
        return f'{label}. Attendance was recorded with low GPS accuracy and is pending review.'
    return f'{label} from mobile'


def _map_url(event: AttendanceEvent):
    if event.latitude and event.longitude:
        return f'https://www.google.com/maps?q={event.latitude},{event.longitude}'
    return None


def _is_missing_sign_out(db: Session, event: AttendanceEvent, now: Optional[datetime] = None):
    if event.action != 'sign_in':
        return bool(getattr(event, 'missing_sign_out', False))
    now = now or now_sa_naive()
    later_sign_out = (
        db.query(AttendanceEvent)
        .filter(
            AttendanceEvent.user_id == event.user_id,
            AttendanceEvent.action == 'sign_out',
            AttendanceEvent.created_at > event.created_at,
        )
        .order_by(AttendanceEvent.created_at.asc())
        .first()
    )
    cutoff = event.created_at.replace(hour=SHIFT_END_HOUR, minute=SHIFT_END_GRACE_MINUTES, second=0, microsecond=0)
    return later_sign_out is None and now > cutoff




def _split_full_name(full_name: str | None):
    value = (full_name or '').strip()
    if not value:
        return None, None
    parts = value.split()
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])


def _user_display_context(db: Session, user_id: int) -> dict:
    user = db.execute(text("""
        SELECT id, full_name, email
        FROM users
        WHERE id = :user_id
    """), {'user_id': user_id}).mappings().first()
    employee = db.execute(text("""
        SELECT name, surname, email, employee_role
        FROM employee_users
        WHERE user_id = :user_id
        LIMIT 1
    """), {'user_id': user_id}).mappings().first()
    manager = db.execute(text("""
        SELECT name, surname, email
        FROM manager_users
        WHERE user_id = :user_id
        LIMIT 1
    """), {'user_id': user_id}).mappings().first()

    source = employee or manager
    name = (source.get('name') if source else None) or None
    surname = (source.get('surname') if source else None) or None
    if not name and user:
        name, surname = _split_full_name(user.get('full_name'))
    full_name = ' '.join(part for part in [name, surname] if part).strip()
    if not full_name and user:
        full_name = user.get('full_name') or f'User #{user_id}'
    role = (employee.get('employee_role') if employee else None)
    staff_type = 'Employee' if employee else ('Manager' if manager else None)
    return {
        'user_name': name,
        'user_surname': surname,
        'user_full_name': full_name or f'User #{user_id}',
        'user_email': (source.get('email') if source and source.get('email') else (user.get('email') if user else None)),
        'user_role': role,
        'user_staff_type': staff_type,
    }

def _event_to_item(db: Session, event: AttendanceEvent):
    display = _user_display_context(db, event.user_id)
    return {
        'id': event.id,
        'user_id': event.user_id,
        **display,
        'action': event.action,
        'latitude': event.latitude,
        'longitude': event.longitude,
        'accuracy_meters': event.accuracy_meters,
        'distance_from_site_m': float(event.distance_from_site_m) if event.distance_from_site_m is not None else None,
        'gps_status': event.gps_status,
        'is_late': bool(event.is_late),
        'late_minutes': int(event.late_minutes or 0),
        'left_early': bool(event.left_early),
        'early_leave_minutes': int(event.early_leave_minutes or 0),
        'missing_sign_out': _is_missing_sign_out(db, event),
        'attendance_status': event.attendance_status,
        'approval_status': getattr(event, 'approval_status', None) or 'pending',
        'work_location_type': getattr(event, 'work_location_type', None),
        'employee_note': getattr(event, 'employee_note', None),
        'manager_note': getattr(event, 'manager_note', None),
        'approved_by_user_id': getattr(event, 'approved_by_user_id', None),
        'approved_at': event.approved_at.isoformat() if getattr(event, 'approved_at', None) else None,
        'rejected_reason': getattr(event, 'rejected_reason', None),
        'signature_status': getattr(event, 'signature_status', None),
        'photo_status': getattr(event, 'photo_status', None),
        'qr_area_id': getattr(event, 'qr_area_id', None),
        'qr_office_name': getattr(event, 'qr_office_name', None),
        'created_at': event.created_at.isoformat(),
        'map_url': _map_url(event),
    }


def _filtered_events(db: Session, requested_user_ids, from_date: Optional[str], to_date: Optional[str], ascending: bool = False):
    if isinstance(requested_user_ids, int):
        requested_user_ids = [requested_user_ids]
    requested_user_ids = [int(uid) for uid in requested_user_ids if uid is not None]
    if not requested_user_ids:
        return []
    query = db.query(AttendanceEvent).filter(AttendanceEvent.user_id.in_(requested_user_ids))
    if from_date:
        query = query.filter(AttendanceEvent.created_at >= datetime.fromisoformat(from_date))
    if to_date:
        end = datetime.fromisoformat(to_date) + timedelta(days=1)
        query = query.filter(AttendanceEvent.created_at < end)
    order = AttendanceEvent.created_at.asc() if ascending else AttendanceEvent.created_at.desc()
    return query.order_by(order).limit(1000).all()


def _filtered_session_events(db: Session, requested_user_ids, from_date: Optional[str], to_date: Optional[str]):
    """Include open sessions that began before the selected date window."""
    if isinstance(requested_user_ids, int):
        requested_user_ids = [requested_user_ids]
    requested_user_ids = [int(uid) for uid in requested_user_ids if uid is not None]
    events = _filtered_events(db, requested_user_ids, from_date, to_date, ascending=True)
    if not requested_user_ids or not from_date:
        return events

    start = datetime.fromisoformat(from_date)
    included_ids = {event.id for event in events}
    prior_rows = (
        db.query(AttendanceEvent)
        .filter(
            AttendanceEvent.user_id.in_(requested_user_ids),
            AttendanceEvent.created_at < start,
        )
        .order_by(AttendanceEvent.user_id.asc(), AttendanceEvent.created_at.desc())
        .all()
    )
    latest_prior_by_user = {}
    for event in prior_rows:
        latest_prior_by_user.setdefault(event.user_id, event)
    for event in latest_prior_by_user.values():
        if event.action == 'sign_in' and event.id not in included_ids:
            events.append(event)
    return sorted(events, key=lambda event: event.created_at)


def _session_status(sign_in: Optional[AttendanceEvent], sign_out: Optional[AttendanceEvent], missing_sign_out: bool):
    statuses = [getattr(sign_in, 'gps_status', None), getattr(sign_out, 'gps_status', None)]
    if missing_sign_out:
        return 'missing_sign_out'
    if 'outside_area' in statuses:
        return 'outside_area'
    if 'accuracy_too_low' in statuses:
        return 'accuracy_too_low'
    if sign_in and getattr(sign_in, 'is_late', False):
        return 'late'
    if sign_out and getattr(sign_out, 'left_early', False):
        return 'early_leave'
    if sign_in and sign_out:
        return 'complete'
    return 'open'


def _session_approval(sign_in: Optional[AttendanceEvent], sign_out: Optional[AttendanceEvent]):
    values = [getattr(sign_in, 'approval_status', None), getattr(sign_out, 'approval_status', None)]
    if 'rejected' in values:
        return 'rejected'
    if values and all(v == 'approved' for v in values if v):
        return 'approved'
    return 'pending'


def _build_sessions(db: Session, events: list[AttendanceEvent]):
    sessions = []
    now = now_sa_naive()
    by_user = {}
    for event in events:
        by_user.setdefault(event.user_id, []).append(event)
    for _user_id, user_events in by_user.items():
        open_sign_in: Optional[AttendanceEvent] = None
        orphan_counter = 0
        for event in sorted(user_events, key=lambda e: e.created_at):
            if event.action == 'sign_in':
                if open_sign_in is not None:
                    sessions.append(_make_session(open_sign_in, None, _is_missing_sign_out(db, open_sign_in, now), db=db))
                open_sign_in = event
            elif event.action == 'sign_out':
                if open_sign_in is not None:
                    sessions.append(_make_session(open_sign_in, event, False, db=db))
                    open_sign_in = None
                else:
                    orphan_counter += 1
                    sessions.append(_make_session(None, event, False, orphan_counter=orphan_counter, db=db))
        if open_sign_in is not None:
            sessions.append(_make_session(open_sign_in, None, _is_missing_sign_out(db, open_sign_in, now), db=db))
    return sorted(sessions, key=lambda row: row.get('sign_in_at') or row.get('sign_out_at') or '', reverse=True)


def _make_session(sign_in: Optional[AttendanceEvent], sign_out: Optional[AttendanceEvent], missing_sign_out: bool, orphan_counter: int = 0, db: Optional[Session] = None):
    user_id = sign_in.user_id if sign_in else sign_out.user_id
    duration_minutes = None
    if sign_in and sign_out:
        duration_minutes = max(0, int((sign_out.created_at - sign_in.created_at).total_seconds() // 60))
    status_value = _session_status(sign_in, sign_out, missing_sign_out)
    gps_status = getattr(sign_out, 'gps_status', None) or getattr(sign_in, 'gps_status', None)
    session_id = f'session-{sign_in.id if sign_in else "orphan"}-{sign_out.id if sign_out else "open"}-{orphan_counter}'
    work_location_type = getattr(sign_out, 'work_location_type', None) or getattr(sign_in, 'work_location_type', None)
    display = _user_display_context(db, user_id) if db is not None else {}
    return {
        'session_id': session_id,
        'user_id': user_id,
        **display,
        'sign_in_event_id': sign_in.id if sign_in else None,
        'sign_out_event_id': sign_out.id if sign_out else None,
        'sign_in_at': sign_in.created_at.isoformat() if sign_in else None,
        'sign_out_at': sign_out.created_at.isoformat() if sign_out else None,
        'duration_minutes': duration_minutes,
        'status': status_value,
        'gps_status': gps_status,
        'approval_status': _session_approval(sign_in, sign_out),
        'work_location_type': work_location_type,
        'is_late': bool(getattr(sign_in, 'is_late', False)),
        'late_minutes': int(getattr(sign_in, 'late_minutes', 0) or 0),
        'left_early': bool(getattr(sign_out, 'left_early', False)),
        'early_leave_minutes': int(getattr(sign_out, 'early_leave_minutes', 0) or 0),
        'missing_sign_out': missing_sign_out,
        'sign_in_map_url': _map_url(sign_in) if sign_in else None,
        'sign_out_map_url': _map_url(sign_out) if sign_out else None,
        '_sign_in_event': sign_in,
        '_sign_out_event': sign_out,
    }


def _make_no_attendance_session(db: Session, user_id: int):
    display = _user_display_context(db, user_id)
    return {
        'session_id': f'no-attendance-{user_id}',
        'user_id': int(user_id),
        **display,
        'sign_in_event_id': None,
        'sign_out_event_id': None,
        'sign_in_at': None,
        'sign_out_at': None,
        'duration_minutes': None,
        'status': 'no_attendance',
        'gps_status': None,
        'approval_status': None,
        'work_location_type': None,
        'is_late': False,
        'late_minutes': 0,
        'left_early': False,
        'early_leave_minutes': 0,
        'missing_sign_out': False,
        'sign_in_map_url': None,
        'sign_out_map_url': None,
    }


def _include_users_without_sessions(db: Session, sessions: list[dict], requested_user_ids: list[int]):
    seen = {int(row.get('user_id')) for row in sessions if row.get('user_id') is not None}
    for uid in requested_user_ids:
        if int(uid) not in seen:
            sessions.append(_make_no_attendance_session(db, int(uid)))
    return sorted(
        sessions,
        key=lambda row: (row.get('sign_in_at') or row.get('sign_out_at') or '', row.get('user_full_name') or ''),
        reverse=True,
    )


def _session_summary(sessions: list[dict]):
    real_sessions = [s for s in sessions if s.get('status') != 'no_attendance']
    return {
        'total_sessions': len(real_sessions),
        'completed_sessions': sum(1 for s in real_sessions if s.get('sign_in_at') and s.get('sign_out_at')),
        'open_sessions': sum(1 for s in real_sessions if s.get('sign_in_at') and not s.get('sign_out_at')),
        'missing_sign_out': sum(1 for s in real_sessions if s.get('missing_sign_out')),
        'late_sessions': sum(1 for s in real_sessions if s.get('is_late')),
        'early_leave_sessions': sum(1 for s in real_sessions if s.get('left_early')),
        'outside_area': sum(1 for s in real_sessions if s.get('status') == 'outside_area'),
        'low_accuracy': sum(1 for s in real_sessions if s.get('status') == 'accuracy_too_low'),
        'pending_approval': sum(1 for s in real_sessions if s.get('approval_status') == 'pending'),
        'approved': sum(1 for s in real_sessions if s.get('approval_status') == 'approved'),
        'rejected': sum(1 for s in real_sessions if s.get('approval_status') == 'rejected'),
        'total_minutes': sum(int(s.get('duration_minutes') or 0) for s in real_sessions),
    }


@router.get('/status', response_model=AttendanceStatusResponse)
def attendance_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_employee_access(db, current_user)
    last = _get_last_event(db, current_user.id)
    current_status = 'signed_in' if last and last.action == 'sign_in' else 'signed_out'
    return AttendanceStatusResponse(current_status=current_status, last_action=last.action if last else None, last_action_at=last.created_at.isoformat() if last else None)


@router.get('/franchises')
def visible_history_franchises(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles = set(_get_role_names(db, current_user.id))
    items = []
    if 'SuperUser' in roles:
        approved = db.execute(text("""
            SELECT fu.id AS franchise_id,
                   COALESCE(fu.franchise_name, u.full_name, u.email, 'Franchise') AS label,
                   u.email AS email,
                   'approved' AS status
            FROM franchise_users fu
            LEFT JOIN users u ON u.id = fu.user_id
            ORDER BY label
        """)).mappings().all()
        items.extend(dict(row) for row in approved)
        registrations = db.execute(text("""
            SELECT NULL AS franchise_id,
                   COALESCE(trading_as, business_name, franchisee_name || ' ' || franchisee_surname, 'Franchise registration') AS label,
                   email,
                   COALESCE(status, 'pending') AS status
            FROM franchise_registrations
            WHERE COALESCE(status, 'pending') <> 'approved'
            ORDER BY created_at DESC
            LIMIT 100
        """)).mappings().all()
        items.extend(dict(row) for row in registrations)
    elif 'FranchiseUser' in roles:
        row = db.execute(text("""
            SELECT fu.id AS franchise_id,
                   COALESCE(fu.franchise_name, u.full_name, u.email, 'My franchise') AS label,
                   u.email AS email,
                   'approved' AS status
            FROM franchise_users fu
            LEFT JOIN users u ON u.id = fu.user_id
            WHERE fu.user_id = :uid
            LIMIT 1
        """), {'uid': current_user.id}).mappings().first()
        if row: items.append(dict(row))
    elif 'ManagerUser' in roles:
        row = db.execute(text("""
            SELECT fu.id AS franchise_id,
                   COALESCE(fu.franchise_name, u.full_name, u.email, 'My franchise') AS label,
                   u.email AS email,
                   'approved' AS status
            FROM manager_users mu
            JOIN franchise_users fu ON fu.id = mu.franchise_user_id
            LEFT JOIN users u ON u.id = fu.user_id
            WHERE mu.user_id = :uid
            LIMIT 1
        """), {'uid': current_user.id}).mappings().first()
        if row: items.append(dict(row))
    return {'items': items}

@router.get('/history', response_model=AttendanceHistoryResponse)
def attendance_history(user_id: Optional[int] = Query(default=None), franchise_id: Optional[int] = Query(default=None), from_date: Optional[str] = Query(default=None), to_date: Optional[str] = Query(default=None), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user_id:
        _can_view_requested_user(db, current_user, user_id)
        requested_user_ids = [user_id]
    else:
        requested_user_ids = _visible_attendance_user_ids(db, current_user, franchise_id=franchise_id)
    events = _filtered_events(db, requested_user_ids, from_date, to_date, ascending=False)
    return {'items': [_event_to_item(db, event) for event in events]}


@router.get('/sessions', response_model=AttendanceSessionsResponse)
def attendance_sessions(user_id: Optional[int] = Query(default=None), franchise_id: Optional[int] = Query(default=None), from_date: Optional[str] = Query(default=None), to_date: Optional[str] = Query(default=None), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user_id:
        _can_view_requested_user(db, current_user, user_id)
        requested_user_ids = [user_id]
    else:
        requested_user_ids = _visible_attendance_user_ids(db, current_user, franchise_id=franchise_id)
    events = _filtered_session_events(db, requested_user_ids, from_date, to_date)
    sessions = _build_sessions(db, events)
    if not user_id:
        sessions = _include_users_without_sessions(db, sessions, requested_user_ids)
    return {'items': sessions, 'summary': _session_summary(sessions)}

@router.get('/visible-users')
def visible_attendance_users(franchise_id: Optional[int] = Query(default=None), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = _visible_attendance_user_ids(db, current_user, franchise_id=franchise_id)
    items = []
    for uid in ids:
        display = _user_display_context(db, uid)
        items.append({
            'user_id': uid,
            'label': display.get('user_full_name') or f'User #{uid}',
            'detail': display.get('user_role') or display.get('user_staff_type') or display.get('user_email') or '',
            'email': display.get('user_email') or '',
            'role': display.get('user_role') or display.get('user_staff_type') or '',
        })
    items.sort(key=lambda x: (x.get('label') or '').lower())
    return {'items': items}


@router.get('/approvals', response_model=ApprovalListResponse)
def approval_list(approval_status: str = Query(default='pending'), user_id: Optional[int] = Query(default=None), franchise_id: Optional[int] = Query(default=None), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_approval_access(db, current_user)
    visible_ids = _visible_attendance_user_ids(db, current_user, franchise_id=franchise_id)
    if user_id:
        _can_view_requested_user(db, current_user, int(user_id))
        if int(user_id) not in [int(x) for x in visible_ids]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Selected user is not in the selected franchise scope')
        visible_ids = [int(user_id)]
    if not visible_ids:
        return {'items': []}
    query = db.query(AttendanceEvent).filter(AttendanceEvent.user_id.in_(visible_ids))
    if approval_status and approval_status != 'all':
        query = query.filter(AttendanceEvent.approval_status == approval_status)
    events = query.order_by(AttendanceEvent.created_at.desc()).limit(500).all()
    return {'items': [_event_to_item(db, event) for event in events]}


@router.get('/events/{event_id}/photo')
def attendance_event_photo(event_id:int,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    event = db.query(AttendanceEvent).filter(AttendanceEvent.id==event_id).first()
    if not event:
        raise HTTPException(status_code=404,detail='Attendance event not found')
    if int(event.user_id) not in [int(x) for x in _visible_attendance_user_ids(db,current_user)]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='You may only view attendance photos in your allowed scope')
    if not getattr(event,'attendance_photo',None):
        raise HTTPException(status_code=404,detail='Attendance photo not available')
    return Response(
        content=bytes(event.attendance_photo),
        media_type=event.attendance_photo_mime or 'image/jpeg',
        headers={'Content-Disposition':f'inline; filename="{event.attendance_photo_filename or f"attendance-{event_id}.jpg"}"'},
    )


def _decide_event(db: Session, event_id: int, current_user: User, decision: str, payload: ApprovalDecisionRequest):
    _require_approval_access(db, current_user)
    event = db.query(AttendanceEvent).filter(AttendanceEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail='Attendance event not found')
    visible_ids = [int(x) for x in _visible_attendance_user_ids(db, current_user)]
    if int(event.user_id) == int(current_user.id):
        raise HTTPException(status_code=400, detail='You cannot approve or reject your own attendance event')
    if int(event.user_id) not in visible_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You may only decide attendance for users in your allowed scope')
    if getattr(event, 'approval_status', None) in ('approved', 'rejected'):
        raise HTTPException(status_code=400, detail='Attendance event was already decided')
    if decision == 'approved':
        event.approval_status = 'approved'
        event.manager_note = payload.manager_note
        event.rejected_reason = None
    else:
        if not payload.rejected_reason:
            raise HTTPException(status_code=400, detail='Rejected reason is required')
        event.approval_status = 'rejected'
        event.manager_note = payload.manager_note
        event.rejected_reason = payload.rejected_reason
    event.approved_by_user_id = current_user.id
    event.approved_at = now_sa_naive()
    db.commit()
    db.refresh(event)
    staff = db.execute(text("SELECT email FROM users WHERE id=:id"), {'id':int(event.user_id)}).mappings().first()
    create_notification(
        db,
        notification_type=f'attendance_{decision}',
        subject=f'Attendance {decision}',
        message=f'Your {event.action.replace("_"," ")} attendance event #{event.id} was {decision}.',
        recipient_email=staff.get('email') if staff else None,
        related_table='attendance_events',
        related_id=int(event.id),
        user_id=int(event.user_id),
        recipient_user_id=int(event.user_id),
        severity='success' if decision=='approved' else 'danger',
        target_tab='history',
        send_email=True,
    )
    return _event_to_item(db, event)


@router.post('/events/{event_id}/approve')
def approve_event(event_id: int, payload: ApprovalDecisionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _decide_event(db, event_id, current_user, 'approved', payload)


@router.post('/events/{event_id}/reject')
def reject_event(event_id: int, payload: ApprovalDecisionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _decide_event(db, event_id, current_user, 'rejected', payload)




def _prepare_pdf_photo_bytes(photo_bytes, target_ratio=0.82):
    """Crop legacy/full uploaded photos to the same portrait frame used by the staff ID photo.
    The frontend saves aligned crops, but this fallback keeps PDF exports consistent for existing records.
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


def _profile_photo_pdf_image(ctx, width_mm=28, height_mm=34):
    try:
        from reportlab.lib.units import mm
        from reportlab.platypus import Image
    except Exception:
        return None
    photo = None
    if ctx.get('employee') and ctx['employee'].get('profile_photo'):
        photo = ctx['employee'].get('profile_photo')
    elif ctx.get('manager') and ctx['manager'].get('profile_photo'):
        photo = ctx['manager'].get('profile_photo')
    elif ctx.get('user') and ctx['user'].get('profile_photo'):
        photo = ctx['user'].get('profile_photo')
    if not photo:
        return None
    try:
        cropped = _prepare_pdf_photo_bytes(photo, target_ratio=float(width_mm) / float(height_mm))
        return Image(io.BytesIO(cropped), width=width_mm*mm, height=height_mm*mm)
    except Exception:
        return None


def _qr_pdf_status(event):
    if not event:
        return 'No QR scan'
    office = getattr(event, 'qr_office_name', None)
    if office:
        return f"QR: verified at {office}"
    return 'QR: not scanned'

def _safe_text(value):
    if value is None or value == '':
        return 'n/a'
    return str(value)


def _format_pdf_time(value):
    if not value:
        return 'n/a'
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return value
    return format_sa_datetime(value)


def _lookup_selected_user_context(db: Session, selected_user_id: int):
    user = db.execute(text("""
        SELECT id, full_name, email, COALESCE(is_active, TRUE) AS is_active, profile_photo, profile_photo_mime
        FROM users
        WHERE id = :user_id
    """), {'user_id': selected_user_id}).mappings().first()
    if not user:
        raise HTTPException(status_code=404, detail='Selected user was not found')

    roles = [row['name'] for row in db.execute(text("""
        SELECT r.name
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        WHERE ur.user_id = :user_id
        ORDER BY r.name
    """), {'user_id': selected_user_id}).mappings().all()]

    employee = db.execute(text("""
        SELECT eu.*, a.name AS office_name
        FROM employee_users eu
        LEFT JOIN gps_allocations_per_user g ON g.user_id = eu.user_id AND COALESCE(g.is_active, TRUE) = TRUE
        LEFT JOIN areas a ON a.id = g.area_id
        WHERE eu.user_id = :user_id
        LIMIT 1
    """), {'user_id': selected_user_id}).mappings().first()

    manager = db.execute(text("""
        SELECT mu.*, a.name AS office_name
        FROM manager_users mu
        LEFT JOIN gps_allocations_per_user g ON g.user_id = mu.user_id AND COALESCE(g.is_active, TRUE) = TRUE
        LEFT JOIN areas a ON a.id = g.area_id
        WHERE mu.user_id = :user_id
        LIMIT 1
    """), {'user_id': selected_user_id}).mappings().first()

    employee_manager = None
    franchise_id = None
    if employee:
        franchise_id = employee.get('franchise_user_id')
        if employee.get('manager_user_id'):
            employee_manager = db.execute(text("""
                SELECT mu.*, u.email AS login_email, u.full_name AS login_full_name
                FROM manager_users mu
                LEFT JOIN users u ON u.id = mu.user_id
                WHERE mu.id = :manager_id
                LIMIT 1
            """), {'manager_id': employee.get('manager_user_id')}).mappings().first()
    if manager:
        franchise_id = manager.get('franchise_user_id')
        employee_manager = manager

    franchise = None
    if franchise_id:
        franchise = db.execute(text("""
            SELECT fu.*, u.full_name AS owner_name, u.email AS owner_email
            FROM franchise_users fu
            LEFT JOIN users u ON u.id = fu.user_id
            WHERE fu.id = :franchise_id
            LIMIT 1
        """), {'franchise_id': franchise_id}).mappings().first()
    else:
        franchise = db.execute(text("""
            SELECT fu.*, u.full_name AS owner_name, u.email AS owner_email
            FROM franchise_users fu
            LEFT JOIN users u ON u.id = fu.user_id
            WHERE fu.user_id = :user_id
            LIMIT 1
        """), {'user_id': selected_user_id}).mappings().first()

    return {
        'user': dict(user),
        'roles': roles,
        'employee': dict(employee) if employee else None,
        'manager': dict(employee_manager) if employee_manager else None,
        'franchise': dict(franchise) if franchise else None,
    }


def _pdf_paragraph(text_value, style):
    from reportlab.platypus import Paragraph
    from xml.sax.saxutils import escape
    return Paragraph(escape(_safe_text(text_value)), style)


def _build_attendance_pdf(db: Session, view: str, selected_user_id: int, from_date: Optional[str], to_date: Optional[str], current_user: User) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether

    ctx = _lookup_selected_user_context(db, selected_user_id)
    events = _filtered_events(db, [selected_user_id], from_date, to_date, ascending=True)
    session_events = _filtered_session_events(db, [selected_user_id], from_date, to_date)
    sessions = _build_sessions(db, session_events)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=9 * mm,
        bottomMargin=9 * mm,
        title='Attendance PDF Export',
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Small', parent=styles['Normal'], fontSize=7, leading=9))
    styles.add(ParagraphStyle(name='Tiny', parent=styles['Normal'], fontSize=6, leading=8))
    styles.add(ParagraphStyle(name='HeaderLilac', parent=styles['Heading2'], fontSize=13, leading=15, textColor=colors.HexColor('#2f2b3a')))
    right_style = ParagraphStyle(name='RightSmall', parent=styles['Small'], alignment=TA_RIGHT)

    story = []
    franchise = ctx['franchise'] or {}
    user = ctx['user']
    employee = ctx['employee'] or {}
    manager = ctx['manager'] or {}

    franchise_text = '<b>Franchise Details</b><br/>' + '<br/>'.join([
        f"Name: {_safe_text(franchise.get('franchise_name') or franchise.get('business_name') or 'Martins')}",
        f"Owner: {_safe_text(franchise.get('owner_name'))}",
        f"Email: {_safe_text(franchise.get('owner_email'))}",
        f"Exported by: {_safe_text(current_user.full_name)}",
        f"Date range: {_safe_text(from_date or 'All')} to {_safe_text(to_date or 'All')}",
    ])
    logo_path = Path(__file__).resolve().parents[1] / 'static' / 'logo.png'
    logo_cell = Paragraph('<b>Attendance Register Platform</b>', right_style)
    if logo_path.exists():
        try:
            logo_cell = Image(str(logo_path), width=48 * mm, height=20 * mm, kind='proportional')
        except Exception:
            pass
    top = Table([[Paragraph(franchise_text, styles['Small']), logo_cell]], colWidths=[190 * mm, 80 * mm])
    top.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(top)
    story.append(Spacer(1, 3 * mm))

    detail_rows = [
        ['Selected User', _safe_text(user.get('full_name')), 'Login Email', _safe_text(user.get('email'))],
        ['Roles', ', '.join(ctx['roles']) or 'n/a', 'Active', 'Yes' if user.get('is_active') else 'No'],
        ['Employee Details', f"{_safe_text(employee.get('employee_role'))} - {_safe_text(employee.get('name'))} {_safe_text(employee.get('surname'))}", 'Employee Contact', _safe_text(employee.get('contact_number'))],
        ['Employee Office', _safe_text(employee.get('office_name') or employee.get('office_address_assigned')), 'Employee Email', _safe_text(employee.get('email'))],
        ['Manager Details', f"{_safe_text(manager.get('name') or manager.get('login_full_name'))} {_safe_text(manager.get('surname') or '')}", 'Manager Contact', _safe_text(manager.get('contact_number'))],
        ['Manager Office', _safe_text(manager.get('office_name') or manager.get('office_address_assigned')), 'Manager Email', _safe_text(manager.get('email') or manager.get('login_email'))],
    ]
    detail_table = Table([[ _pdf_paragraph(c, styles['Tiny']) for c in row] for row in detail_rows], colWidths=[32*mm, 100*mm, 32*mm, 100*mm])
    detail_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f4f1fb')),
        ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#ded6ee')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    photo_cell = _profile_photo_pdf_image(ctx)
    if photo_cell is not None:
        profile_table = Table([[photo_cell, detail_table]], colWidths=[34*mm, 235*mm])
        profile_table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'), ('ALIGN',(0,0),(0,0),'CENTER')]))
        story.append(profile_table)
    else:
        story.append(detail_table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"Attendance {view.title()} - selected user only", styles['HeaderLilac']))

    if view == 'events':
        headers = ['Time', 'Action', 'Status', 'GPS', 'QR Office', 'Work', 'Approval', 'Signature', 'Photo', 'Notes']
        data = [headers]
        for event in events:
            status_value = event.attendance_status or event.gps_status or 'recorded'
            data.append([
                _format_pdf_time(event.created_at),
                _safe_text(event.action),
                _safe_text(_gps_report_label(status_value) if status_value in {'inside_area', 'outside_area', 'accuracy_too_low', 'no_allocation', 'on_road'} else status_value),
                _safe_text(_gps_report_label(event.gps_status)),
                _qr_pdf_status(event),
                _safe_text(event.work_location_type),
                _safe_text(event.approval_status),
                _signature_pdf_image(event) or _pdf_paragraph(event.signature_status or 'missing', styles['Tiny']),
                _safe_text(getattr(event, 'photo_status', None) or 'not available'),
                _safe_text(event.employee_note or event.manager_note or event.rejected_reason),
            ])
        col_widths = [26*mm, 17*mm, 22*mm, 22*mm, 31*mm, 18*mm, 22*mm, 34*mm, 18*mm, 54*mm]
    else:
        headers = ['Sign In', 'Sign Out', 'Duration', 'Status', 'GPS', 'QR In', 'QR Out', 'Approval', 'In Signature', 'Out Signature', 'Late', 'Missing']
        data = [headers]
        for session in sessions:
            maps = []
            if session.get('sign_in_map_url'):
                maps.append('In map')
            if session.get('sign_out_map_url'):
                maps.append('Out map')
            data.append([
                _format_pdf_time(session.get('sign_in_at')),
                _format_pdf_time(session.get('sign_out_at')),
                _safe_text(session.get('duration_minutes')),
                _safe_text(_gps_report_label(session.get('status')) if session.get('status') in {'inside_area', 'outside_area', 'accuracy_too_low', 'no_allocation', 'on_road'} else session.get('status')),
                _safe_text(_gps_report_label(session.get('gps_status'))),
                _qr_pdf_status(session.get('_sign_in_event')),
                _qr_pdf_status(session.get('_sign_out_event')),
                _safe_text(session.get('approval_status')), 
                _signature_pdf_image(session.get('_sign_in_event')) or _pdf_paragraph('missing', styles['Tiny']),
                _signature_pdf_image(session.get('_sign_out_event')) or _pdf_paragraph('missing', styles['Tiny']),
                f"{session.get('late_minutes', 0)} min" if session.get('is_late') else 'No',
                'Yes' if session.get('missing_sign_out') else 'No',
            ])
        col_widths = [25*mm, 25*mm, 16*mm, 20*mm, 20*mm, 28*mm, 28*mm, 20*mm, 31*mm, 31*mm, 13*mm, 17*mm]

    def _pdf_cell(c):
        return c if hasattr(c, 'wrap') else _pdf_paragraph(c, styles['Tiny'])
    pdf_table = Table([[ _pdf_cell(c) for c in row] for row in data], repeatRows=1, colWidths=col_widths)
    pdf_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#b99add')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#e6e1ee')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#fbfaff')]),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 3),
        ('RIGHTPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(pdf_table)
    if len(data) == 1:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph('No attendance records found for this selected user and date range.', styles['Small']))

    doc.build(story)
    return buffer.getvalue()


@router.get('/export')
def attendance_export(view: str = Query(default='sessions', pattern='^(sessions|events)$'), user_id: Optional[int] = Query(default=None), from_date: Optional[str] = Query(default=None), to_date: Optional[str] = Query(default=None), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    selected_user_id = int(user_id or current_user.id)
    _can_view_requested_user(db, current_user, selected_user_id)
    try:
        content = _build_attendance_pdf(db, view, selected_user_id, from_date, to_date, current_user)
    except ImportError:
        raise HTTPException(status_code=500, detail='PDF export requires reportlab. Run: pip install -r requirements.txt')
    stamp = now_sa_naive().strftime('%Y%m%d')
    filename = f'attendance_{view}_user_{selected_user_id}_{stamp}.pdf'
    return Response(content=content, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@router.get('/export-batch')
def attendance_export_batch(view: str = Query(default='sessions', pattern='^(sessions|events)$'), user_ids: list[int] = Query(default=[]), from_date: Optional[str] = Query(default=None), to_date: Optional[str] = Query(default=None), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    selected_ids = user_ids or [current_user.id]
    selected_ids = list(dict.fromkeys(int(uid) for uid in selected_ids))
    if len(selected_ids) > 100:
        raise HTTPException(status_code=400, detail='Please export 100 users or fewer at a time')
    for selected_user_id in selected_ids:
        _can_view_requested_user(db, current_user, selected_user_id)
    try:
        zip_buffer = io.BytesIO()
        stamp = now_sa_naive().strftime('%Y%m%d')
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for selected_user_id in selected_ids:
                content = _build_attendance_pdf(db, view, selected_user_id, from_date, to_date, current_user)
                ctx = _lookup_selected_user_context(db, selected_user_id)
                raw_name = ctx['user'].get('full_name') or f'user_{selected_user_id}'
                safe_name = ''.join(ch if ch.isalnum() or ch in (' ', '-', '_') else '_' for ch in raw_name).strip().replace(' ', '_')
                zf.writestr(f'attendance_{view}_{safe_name}_{selected_user_id}_{stamp}.pdf', content)
    except ImportError:
        raise HTTPException(status_code=500, detail='PDF export requires reportlab. Run: pip install -r requirements.txt')
    zip_buffer.seek(0)
    filename = f'attendance_{view}_selected_users_{stamp}.zip'
    return Response(content=zip_buffer.getvalue(), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="{filename}"'})






@router.post('/office-qr/offices')
def create_office(payload: OfficeCreateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles=set(_get_role_names(db,current_user.id))
    if 'FranchiseUser' not in roles and 'SuperUser' not in roles:
        raise HTTPException(status_code=403, detail='Only a franchise user can add an office address')
    fid,_=_franchise_scope_for_user(db,current_user.id)
    if not fid:
        raise HTTPException(status_code=400, detail='Franchise profile required')
    name=str(payload.name or '').strip(); address=str(payload.address or '').strip()
    if not name or not address:
        raise HTTPException(status_code=400, detail='Office name and address are required')
    existing=db.execute(text("SELECT id FROM areas WHERE franchise_user_id=:fid AND LOWER(COALESCE(office_address,description,''))=LOWER(:address) AND COALESCE(is_archived,FALSE)=FALSE"), {'fid':fid,'address':address}).scalar()
    if existing:
        raise HTTPException(status_code=409, detail='This office address already exists')
    token=_generate_office_code(db)
    row=db.execute(text("""INSERT INTO areas(name,code,description,office_address,latitude,longitude,allowed_radius_m,franchise_user_id,qr_token,qr_enabled,is_archived,created_at,updated_at)
      VALUES(:name,:code,:address,:address,:lat,:lng,:radius,:fid,:token,TRUE,FALSE,:now,:now) RETURNING id"""),
      {'name':name,'code':f'OFF-{int(datetime.utcnow().timestamp())}','address':address,'lat':payload.latitude,'lng':payload.longitude,'radius':max(10,int(payload.allowed_radius_m or 100)),'fid':fid,'token':token,'now':now_sa_naive()}).scalar()
    db.commit()
    return {'message':'Office address added','office':_office_qr_row(db,int(row))}

@router.get('/office-qr/offices')
def list_office_qr_codes(
    franchise_user_id: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_office_qr_schema(db)
    roles = set(_get_role_names(db, current_user.id))
    if not roles.intersection({'SuperUser', 'FranchiseUser', 'ManagerUser'}):
        raise HTTPException(status_code=403, detail='Only SuperUser, Franchise or Manager users can print office QR codes')

    params = {}
    where = 'COALESCE(a.is_archived, FALSE) = FALSE'
    if 'SuperUser' in roles and franchise_user_id is None:
        return []
    if 'SuperUser' in roles and franchise_user_id is not None:
        _sync_franchise_address_areas(db, franchise_user_id)
        where = 'a.franchise_user_id = :fid AND COALESCE(a.is_archived, FALSE) = FALSE'
        params['fid'] = franchise_user_id
    elif 'SuperUser' not in roles:
        fid, _ = _franchise_scope_for_user(db, current_user.id)
        if not fid:
            raise HTTPException(status_code=403, detail='No franchise scope found')
        _sync_franchise_address_areas(db, int(fid))
        where = 'a.franchise_user_id = :fid AND COALESCE(a.is_archived, FALSE) = FALSE'
        params['fid'] = int(fid)
        if 'ManagerUser' in roles and 'FranchiseUser' not in roles:
            assigned = db.execute(text("""
                SELECT area_id FROM gps_allocations_per_user
                WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE
                ORDER BY id DESC LIMIT 1
            """), {'uid': current_user.id}).mappings().first()
            where += ' AND a.id = :assigned_area_id'
            params['assigned_area_id'] = int(assigned['area_id']) if assigned and assigned.get('area_id') else -1

    rows = db.execute(text(f"""
        SELECT a.id, a.name, a.code, a.description, a.office_address, a.latitude, a.longitude,
               a.allowed_radius_m, a.qr_token, COALESCE(a.qr_enabled, TRUE) AS qr_enabled,
               COALESCE(a.is_archived, FALSE) AS is_archived, a.archived_at, a.franchise_user_id,
               COUNT(DISTINCT g.user_id) AS assigned_user_count
        FROM areas a
        LEFT JOIN gps_allocations_per_user g ON g.area_id = a.id AND COALESCE(g.is_active, TRUE) = TRUE
        WHERE {where}
        GROUP BY a.id
        ORDER BY COALESCE(a.is_archived, FALSE) ASC, a.created_at DESC, a.name ASC
    """), params).mappings().all()
    result = []
    for raw in rows:
        row = _office_qr_row(db, int(raw['id']))
        result.append({
            'id': row['id'], 'name': row.get('name'), 'code': row.get('code'),
            'address': _office_address(row),
            'latitude': str(row.get('latitude')) if row.get('latitude') is not None else None,
            'longitude': str(row.get('longitude')) if row.get('longitude') is not None else None,
            'allowed_radius_m': row.get('allowed_radius_m'),
            'qr_enabled': row.get('qr_enabled') is not False,
            'is_archived': bool(row.get('is_archived')),
            'archived_at': row.get('archived_at').isoformat() if row.get('archived_at') else None,
            'qr_payload': _qr_payload(row['qr_token']),
            'scan_url': _qr_scan_url(row['qr_token']),
            'qr_valid_week': row.get('qr_valid_week'),
            'qr_valid_until': row.get('qr_valid_until').isoformat() if row.get('qr_valid_until') else None,
            'franchise_user_id': row.get('franchise_user_id'),
            'assigned_user_count': int(raw.get('assigned_user_count') or 0),
        })
    return result


@router.post('/office-qr/validate')
def validate_office_qr(payload: OfficeQrValidateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    area, token = _validate_office_qr_for_user(db, current_user.id, payload.qr_value)
    return {
        'valid': True,
        'area_id': area['id'],
        'office_name': area.get('name'),
        'address': _office_address(area),
        'qr_payload': _qr_payload(token),
        'scan_url': _qr_scan_url(token),
        'latitude': str(area.get('latitude')) if area.get('latitude') is not None else None,
        'longitude': str(area.get('longitude')) if area.get('longitude') is not None else None,
        'allowed_radius_m': int(area.get('allowed_radius_m') or 100),
        'qr_valid_week': area.get('qr_valid_week'),
        'qr_valid_until': area.get('qr_valid_until').isoformat() if area.get('qr_valid_until') else None,
    }


@router.get('/office-qr/{area_id}/pdf')
def print_office_qr_pdf(area_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles = set(_get_role_names(db, current_user.id))
    if not roles.intersection({'SuperUser', 'FranchiseUser', 'ManagerUser'}):
        raise HTTPException(status_code=403, detail='Only SuperUser, Franchise or Manager users can print office QR codes')
    area = _office_qr_row(db, area_id)
    _assert_office_area_access(db, current_user, area)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
        from reportlab.graphics.barcode import qr
        from reportlab.graphics.shapes import Drawing
    except ImportError:
        raise HTTPException(status_code=500, detail='QR PDF export requires reportlab. Run: pip install -r requirements.txt')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=10*mm, leftMargin=10*mm, topMargin=8*mm, bottomMargin=8*mm)
    styles = getSampleStyleSheet()
    brand = colors.HexColor('#6f42c1')
    dark = colors.HexColor('#292536')
    address = _office_address(area) or 'Address not captured'
    office_name = str(area.get('name') or 'Office').split(' [', 1)[0].strip()
    office_code = str(area['qr_token'])
    scan_url = _qr_scan_url(office_code)
    qr_code = qr.QrCodeWidget(scan_url)
    bounds = qr_code.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    size = 86 * mm
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(qr_code)
    title_style = ParagraphStyle('QRTitle', parent=styles['Title'], fontSize=21, leading=24, textColor=dark, alignment=TA_CENTER, spaceAfter=2*mm)
    office_style = ParagraphStyle('OfficeName', parent=styles['Heading1'], fontSize=16, leading=19, textColor=brand, alignment=TA_CENTER, spaceAfter=1*mm)
    center_style = ParagraphStyle('Center', parent=styles['BodyText'], fontSize=9, leading=12, textColor=dark, alignment=TA_CENTER)
    instruction_style = ParagraphStyle('Instruction', parent=center_style, fontSize=11, leading=14)
    logo_path = Path(__file__).resolve().parents[1] / 'static' / 'logo.png'
    header_items = []
    if logo_path.exists():
        header_items.append(Image(str(logo_path), width=76*mm, height=30*mm, kind='proportional'))
    code_style = ParagraphStyle('OfficeCode', parent=styles['Title'], fontSize=34, leading=37, textColor=brand, alignment=TA_CENTER, spaceBefore=1*mm, spaceAfter=1*mm)
    header_items.extend([
        Paragraph('OFFICE ATTENDANCE', title_style),
        Paragraph(office_name, office_style),
        Paragraph(address, center_style),
        Paragraph(f'<b>OFFICE CODE: {office_code}</b>', code_style),
    ])
    header = Table([[item] for item in header_items], colWidths=[186*mm])
    header.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('BOTTOMPADDING',(0,0),(-1,-1),2*mm)]))
    qr_panel = Table([[drawing]], colWidths=[104*mm], rowHeights=[104*mm])
    qr_panel.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('BOX',(0,0),(-1,-1),2,brand),('BACKGROUND',(0,0),(-1,-1),colors.white),('LEFTPADDING',(0,0),(-1,-1),5*mm),('RIGHTPADDING',(0,0),(-1,-1),5*mm),('TOPPADDING',(0,0),(-1,-1),5*mm),('BOTTOMPADDING',(0,0),(-1,-1),5*mm)]))
    validity = area.get('qr_valid_until')
    validity_text = format_sa_datetime(validity) if validity else 'the next weekly rotation'
    footer = Table([
        [Paragraph(f'<b>ENTER CODE {office_code} OR SCAN TO SIGN IN OR SIGN OUT</b>', instruction_style)],
        [Paragraph('Use your registered staff login. The code works only for staff assigned to this office and physically inside its configured GPS radius.', center_style)],
        [Paragraph(f'This code is valid until {validity_text}. A new code is generated automatically each week.', center_style)],
        [Paragraph('GPS location, signature and automatic photo evidence are required to complete attendance.', center_style)],
    ], colWidths=[180*mm])
    footer.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f2ecff')),('BOX',(0,0),(-1,-1),1,colors.HexColor('#ded2f8')),('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),2.5*mm),('BOTTOMPADDING',(0,0),(-1,-1),2.5*mm),('LEFTPADDING',(0,0),(-1,-1),5*mm),('RIGHTPADDING',(0,0),(-1,-1),5*mm)]))
    doc.build([header, Spacer(1,3*mm), qr_panel, Spacer(1,4*mm), footer])
    buffer.seek(0)
    safe_name = ''.join(ch if ch.isalnum() else '_' for ch in office_name).strip('_') or f'office_{area_id}'
    return Response(buffer.getvalue(), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="office_qr_{safe_name}.pdf"'})


@router.post('/office-qr/offices/{area_id}/regenerate')
def regenerate_office_qr(area_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    area = _office_qr_row(db, area_id)
    _assert_office_area_access(db, current_user, area, write=True)
    new_token = _generate_office_code(db, exclude_area_id=area_id)
    now = now_sa_naive()
    valid_week, valid_until = _office_code_week(now)
    db.execute(text("""
        UPDATE areas
        SET qr_token = :token, qr_enabled = TRUE, qr_updated_at = :now,
            qr_valid_week = :valid_week, updated_at = :now
        WHERE id = :area_id
    """), {'token': new_token, 'now': now, 'valid_week': valid_week, 'area_id': area_id})
    db.commit()
    updated = _office_qr_row(db, area_id)
    return {
        'message': 'A new four-digit office code was generated. The previous code is now invalid.',
        'office': updated,
        'valid_until': valid_until.isoformat(),
    }


@router.patch('/office-qr/offices/{area_id}')
def update_office_details(area_id: int, payload: OfficeDetailsUpdateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    area_data = _office_qr_row(db, area_id)
    _assert_office_area_access(db, current_user, area_data, write=True)
    name = str(payload.name or '').strip()
    address = str(payload.address or '').strip()
    if not name or not address:
        raise HTTPException(status_code=400, detail='Office name and address are required')
    radius = max(10, int(payload.allowed_radius_m or 100))
    db.execute(text("UPDATE areas SET name=:name, description=:address, office_address=:address, allowed_radius_m=:radius, updated_at=:now WHERE id=:area_id"), {'name':name,'address':address,'radius':radius,'now':now_sa_naive(),'area_id':area_id})
    db.execute(text("UPDATE gps_allocations_per_user SET radius_meters=:radius, updated_at=:now WHERE area_id=:area_id AND COALESCE(is_active, TRUE)=TRUE"), {'radius':radius,'now':now_sa_naive(),'area_id':area_id})
    if area_data.get('franchise_user_id'):
        current_address = db.execute(text('SELECT office_address FROM franchise_users WHERE id=:fid'), {'fid':area_data['franchise_user_id']}).scalar()
        if _normalise_address(current_address) == _normalise_address(_office_address(area_data)):
            db.execute(text('UPDATE franchise_users SET office_address=:address, updated_at=:now WHERE id=:fid'), {'address':address,'now':now_sa_naive(),'fid':area_data['franchise_user_id']})
    db.commit()
    return {'message':'Office updated','office':_office_qr_row(db, area_id)}


@router.get('/office-qr/offices/{area_id}/linked-staff')
def office_linked_staff(area_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    area = _office_qr_row(db, area_id)
    _assert_office_area_access(db, current_user, area, write=True)
    rows = db.execute(text("""
        SELECT 'employee' AS staff_type, eu.id AS staff_id, eu.user_id,
               TRIM(COALESCE(eu.name, '') || ' ' || COALESCE(eu.surname, '')) AS full_name,
               eu.employee_number, eu.office_address_assigned
        FROM employee_users eu
        JOIN gps_allocations_per_user ga ON ga.user_id = eu.user_id
        WHERE ga.area_id = :area_id AND COALESCE(ga.is_active, TRUE) = TRUE AND COALESCE(eu.is_active, TRUE) = TRUE
        UNION ALL
        SELECT 'manager' AS staff_type, mu.id AS staff_id, mu.user_id,
               TRIM(COALESCE(mu.name, '') || ' ' || COALESCE(mu.surname, '')) AS full_name,
               mu.employee_number, mu.office_address_assigned
        FROM manager_users mu
        JOIN gps_allocations_per_user ga ON ga.user_id = mu.user_id
        WHERE ga.area_id = :area_id AND COALESCE(ga.is_active, TRUE) = TRUE AND COALESCE(mu.is_active, TRUE) = TRUE
        ORDER BY full_name
    """), {'area_id': area_id}).mappings().all()
    return {'office': area, 'items': [dict(row) for row in rows], 'count': len(rows)}


@router.post('/office-qr/offices/{area_id}/reassign-linked-staff')
def reassign_linked_staff(area_id: int, payload: OfficeReassignRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    area = _office_qr_row(db, area_id)
    _assert_office_area_access(db, current_user, area, write=True)
    new_address = str(payload.new_address or '').strip()
    if not new_address:
        raise HTTPException(status_code=400, detail='A replacement address is required')
    replacement = None
    if payload.new_area_id:
        replacement = _office_qr_row(db, int(payload.new_area_id))
        _assert_office_area_access(db, current_user, replacement, write=True)
        if replacement.get('is_archived') or int(replacement['id']) == int(area_id):
            raise HTTPException(status_code=400, detail='Select a different active registered address')
        new_address = _office_address(replacement)
    assigned_count = db.execute(text('SELECT COUNT(*) FROM gps_allocations_per_user WHERE area_id=:area_id AND COALESCE(is_active, TRUE)=TRUE'), {'area_id': area_id}).scalar() or 0
    now = now_sa_naive()
    if assigned_count:
        db.execute(text('''
            UPDATE employee_users SET office_address_assigned=:address, updated_at=:now
            WHERE user_id IN (SELECT user_id FROM gps_allocations_per_user WHERE area_id=:area_id AND COALESCE(is_active, TRUE)=TRUE)
        '''), {'address': new_address, 'now': now, 'area_id': area_id})
        db.execute(text('''
            UPDATE manager_users SET office_address_assigned=:address, updated_at=:now
            WHERE user_id IN (SELECT user_id FROM gps_allocations_per_user WHERE area_id=:area_id AND COALESCE(is_active, TRUE)=TRUE)
        '''), {'address': new_address, 'now': now, 'area_id': area_id})
        if replacement:
            db.execute(text('UPDATE gps_allocations_per_user SET area_id=:new_area_id, updated_at=:now WHERE area_id=:area_id AND COALESCE(is_active, TRUE)=TRUE'), {'new_area_id': replacement['id'], 'now': now, 'area_id': area_id})
        else:
            db.execute(text('UPDATE gps_allocations_per_user SET is_active=FALSE, updated_at=:now WHERE area_id=:area_id AND COALESCE(is_active, TRUE)=TRUE'), {'now': now, 'area_id': area_id})
    if area.get('franchise_user_id'):
        db.execute(text('UPDATE franchise_users SET office_address=:address, updated_at=:now WHERE id=:fid'), {'address': new_address, 'now': now, 'fid': area['franchise_user_id']})
        email = db.execute(text('SELECT u.email FROM franchise_users fu JOIN users u ON u.id=fu.user_id WHERE fu.id=:fid'), {'fid': area['franchise_user_id']}).scalar()
        if email:
            db.execute(text('UPDATE franchise_registrations SET office_address=:address, updated_at=:now WHERE LOWER(email)=LOWER(:email)'), {'address': new_address, 'now': now, 'email': email})
    db.commit()
    return {'message': 'Linked staff were moved to the replacement address and detached from this office.', 'updated_staff': int(assigned_count)}


@router.delete('/office-qr/offices/{area_id}')
def delete_office(area_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    area = _office_qr_row(db, area_id)
    _assert_office_area_access(db, current_user, area, write=True)
    assigned = db.execute(text('SELECT COUNT(*) FROM gps_allocations_per_user WHERE area_id=:area_id AND COALESCE(is_active, TRUE)=TRUE'), {'area_id':area_id}).scalar() or 0
    if assigned:
        raise HTTPException(status_code=409, detail=f'Cannot delete this office while {assigned} active staff member(s) are assigned to it. Edit those staff addresses first.')
    now = now_sa_naive()
    db.execute(text('''
        UPDATE areas
        SET is_archived=TRUE, archived_at=:now, qr_enabled=FALSE, updated_at=:now
        WHERE id=:area_id
    '''), {'now': now, 'area_id': area_id})
    db.commit()
    return {
        'message': 'Office address archived. Historical office, QR and allocation records were preserved.',
        'area_id': area_id,
        'archived': True,
    }

def _assert_office_area_access(db: Session, current_user: User, area: dict, write: bool = False):
    roles = set(_get_role_names(db, current_user.id))
    if 'SuperUser' in roles:
        return
    fid, _ = _franchise_scope_for_user(db, current_user.id)
    if not fid or int(area.get('franchise_user_id') or 0) != int(fid):
        raise HTTPException(status_code=403, detail='This office QR code is outside your franchise scope')
    if 'ManagerUser' in roles and 'FranchiseUser' not in roles:
        allocation = db.execute(text("""
            SELECT area_id FROM gps_allocations_per_user
            WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE
            ORDER BY id DESC LIMIT 1
        """), {'uid': current_user.id}).mappings().first()
        if not allocation or int(allocation.get('area_id') or 0) != int(area['id']):
            raise HTTPException(status_code=403, detail='Managers can only access the QR code for their assigned office')
        if write:
            raise HTTPException(status_code=403, detail='Only the franchise user can change office GPS settings')

def _get_user_office_hours(db: Session, user_id: int) -> tuple[str, str]:
    # Returns the staff-specific office hours if configured. Falls back to 08:00-17:00.
    try:
        db.execute(text("ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS work_start_time VARCHAR(5) DEFAULT '08:00'"))
        db.execute(text("ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS work_end_time VARCHAR(5) DEFAULT '17:00'"))
        db.execute(text("ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS work_start_time VARCHAR(5) DEFAULT '08:00'"))
        db.execute(text("ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS work_end_time VARCHAR(5) DEFAULT '17:00'"))
        row = db.execute(text("""
            SELECT COALESCE(work_start_time, '08:00') AS work_start_time,
                   COALESCE(work_end_time, '17:00') AS work_end_time
            FROM employee_users WHERE user_id = :user_id
            UNION ALL
            SELECT COALESCE(work_start_time, '08:00') AS work_start_time,
                   COALESCE(work_end_time, '17:00') AS work_end_time
            FROM manager_users WHERE user_id = :user_id
            LIMIT 1
        """), {"user_id": user_id}).mappings().first()
        return ((row.get('work_start_time') if row else None) or '08:00', (row.get('work_end_time') if row else None) or '17:00')
    except Exception:
        return ('08:00', '17:00')


def _time_on_today(now: datetime, hhmm: str, fallback_hour: int) -> datetime:
    try:
        hour, minute = [int(part) for part in str(hhmm).split(':', 1)]
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except Exception:
        return now.replace(hour=fallback_hour, minute=0, second=0, microsecond=0)
    
@router.patch('/office-qr/offices/{area_id}/location')
def update_office_location(
    area_id: int,
    payload: OfficeLocationUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    roles = set(_get_role_names(db, current_user.id))
    if not roles.intersection({'SuperUser', 'FranchiseUser', 'ManagerUser'}):
        raise HTTPException(status_code=403, detail='Only SuperUser, Franchise or Manager users can update office GPS')

    area_data = _office_qr_row(db, area_id)
    _assert_office_area_access(db, current_user, area_data, write=True)
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail='Office / area not found')

    area.latitude = str(payload.latitude)
    area.longitude = str(payload.longitude)
    area.allowed_radius_m = int(payload.allowed_radius_m or 100)

    db.commit()
    db.refresh(area)
    db.execute(text("""
        UPDATE gps_allocations_per_user
        SET latitude = :latitude, longitude = :longitude, radius_meters = :radius, updated_at = :now
        WHERE area_id = :area_id AND COALESCE(is_active, TRUE) = TRUE
    """), {'latitude': str(payload.latitude), 'longitude': str(payload.longitude),
             'radius': int(payload.allowed_radius_m or 100), 'now': now_sa_naive(), 'area_id': area_id})
    db.commit()

    return {
        'id': area.id,
        'latitude': area.latitude,
        'longitude': area.longitude,
        'allowed_radius_m': area.allowed_radius_m,
    }

@router.post('/sign-in', response_model=AttendanceActionResponse)
def sign_in(payload: AttendanceActionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_attendance_signature_columns(db)
    _validate_rules(db, current_user, payload, True)
    qr_area = None
    qr_token = None
    if (payload.work_location_type or 'office') == 'office':
        qr_area, qr_token = _validate_office_qr_for_user(db, current_user.id, payload.qr_value)
    last = _get_last_event(db, current_user.id)
    if last and last.action == 'sign_in':
        raise HTTPException(status_code=400, detail='Already signed in')
    gps_status, distance = _validate_gps(db, current_user.id, payload, office_area_id=(int(qr_area['id']) if qr_area else None))
    approval_status, work_location_type, signature_status = _approval_defaults(payload, gps_status)
    rule = db.query(TimeRegistrarRule).filter(TimeRegistrarRule.is_active == True).first()
    now = now_sa_naive()
    work_start_time, work_end_time = _get_user_office_hours(db, current_user.id)
    shift_start = _time_on_today(now, work_start_time, 8)
    is_late = False
    late_minutes = 0
    if rule:
        diff = (now - shift_start).total_seconds() / 60
        if diff > rule.late_after_minutes:
            is_late = True
            late_minutes = int(diff)
    attendance_status = 'present'
    if gps_status == 'outside_area':
        attendance_status = 'outside_area'
    elif gps_status == 'accuracy_too_low':
        attendance_status = 'accuracy_too_low'
    elif is_late:
        attendance_status = 'late'
    accuracy = _payload_accuracy(payload)
    signature_image, signature_mime, signature_filename = _signature_data_url_to_image(payload.signature_value, 'sign_in', current_user.id)
    photo, photo_mime, photo_filename = _photo_data_url_to_image(payload.photo_value, 'sign_in', current_user.id)
    event = AttendanceEvent(user_id=current_user.id, action='sign_in', latitude=str(payload.latitude) if payload.latitude is not None else None, longitude=str(payload.longitude) if payload.longitude is not None else None, accuracy_meters=str(accuracy) if accuracy is not None else None, device_info=payload.device_info, signature_value=payload.signature_value, signature_image=signature_image, signature_image_mime=signature_mime, signature_image_filename=signature_filename, attendance_photo=photo, attendance_photo_mime=photo_mime, attendance_photo_filename=photo_filename, photo_status='captured', source='mobile_qr' if qr_area else 'mobile_gps', qr_area_id=(int(qr_area['id']) if qr_area else None), qr_office_name=(qr_area.get('name') if qr_area else None), qr_token_hash=_token_hash(qr_token), distance_from_site_m=distance, gps_status=gps_status, is_late=is_late, late_minutes=late_minutes, missing_sign_out=False, attendance_status=attendance_status, approval_status=approval_status, work_location_type=work_location_type, employee_note=payload.employee_note, signature_required=True, signature_status=signature_status)
    db.add(event)
    db.commit()
    db.refresh(event)
    _notify_franchise_attendance_event(db, event, 'sign in')
    return AttendanceActionResponse(message=_attendance_action_message('sign_in', gps_status), action='sign_in', current_status='signed_in')


@router.post('/sign-out', response_model=AttendanceActionResponse)
def sign_out(payload: AttendanceActionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_attendance_signature_columns(db)
    _validate_rules(db, current_user, payload, False)
    qr_area = None
    qr_token = None
    if (payload.work_location_type or 'office') == 'office':
        qr_area, qr_token = _validate_office_qr_for_user(db, current_user.id, payload.qr_value)
    last = _get_last_event(db, current_user.id)
    if not last or last.action != 'sign_in':
        raise HTTPException(status_code=400, detail='Must sign in before signing out')
    gps_status, distance = _validate_gps(db, current_user.id, payload, office_area_id=(int(qr_area['id']) if qr_area else None))
    approval_status, work_location_type, signature_status = _approval_defaults(payload, gps_status)
    rule = db.query(TimeRegistrarRule).filter(TimeRegistrarRule.is_active == True).first()
    now = now_sa_naive()
    work_start_time, work_end_time = _get_user_office_hours(db, current_user.id)
    shift_end = _time_on_today(now, work_end_time, 17)
    left_early = False
    early_minutes = 0
    if rule:
        diff = (shift_end - now).total_seconds() / 60
        if diff > rule.early_leave_before_minutes:
            left_early = True
            early_minutes = int(diff)
    attendance_status = 'signed_out'
    if gps_status == 'outside_area':
        attendance_status = 'outside_area'
    elif gps_status == 'accuracy_too_low':
        attendance_status = 'accuracy_too_low'
    elif left_early:
        attendance_status = 'early_leave'
    accuracy = _payload_accuracy(payload)
    signature_image, signature_mime, signature_filename = _signature_data_url_to_image(payload.signature_value, 'sign_out', current_user.id)
    photo, photo_mime, photo_filename = _photo_data_url_to_image(payload.photo_value, 'sign_out', current_user.id)
    event = AttendanceEvent(user_id=current_user.id, action='sign_out', latitude=str(payload.latitude) if payload.latitude is not None else None, longitude=str(payload.longitude) if payload.longitude is not None else None, accuracy_meters=str(accuracy) if accuracy is not None else None, device_info=payload.device_info, signature_value=payload.signature_value, signature_image=signature_image, signature_image_mime=signature_mime, signature_image_filename=signature_filename, attendance_photo=photo, attendance_photo_mime=photo_mime, attendance_photo_filename=photo_filename, photo_status='captured', source='mobile_qr' if qr_area else 'mobile_gps', qr_area_id=(int(qr_area['id']) if qr_area else None), qr_office_name=(qr_area.get('name') if qr_area else None), qr_token_hash=_token_hash(qr_token), distance_from_site_m=distance, gps_status=gps_status, left_early=left_early, early_leave_minutes=early_minutes, missing_sign_out=False, attendance_status=attendance_status, approval_status=approval_status, work_location_type=work_location_type, employee_note=payload.employee_note, signature_required=True, signature_status=signature_status)
    db.add(event)
    db.commit()
    db.refresh(event)
    _notify_franchise_attendance_event(db, event, 'sign out')
    return AttendanceActionResponse(message=_attendance_action_message('sign_out', gps_status), action='sign_out', current_status='signed_out')
