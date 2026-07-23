from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.core import User, UserRole

router = APIRouter()

PROTECTED_SUPERUSER_EMAIL = "wjm@martinsdirect.com"


def _roles(db: Session, user: User) -> list[str]:
    return [ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]


def _require_superuser(db: Session, user: User):
    if "SuperUser" not in _roles(db, user):
        raise HTTPException(status_code=403, detail="Only SuperUser can manage all system users")


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



def _user_identity_values(db: Session, user_id: int, staff_type: str | None = None, staff_id: int | None = None) -> dict:
    """Collect names/emails/codes used in old notifications or denormalized rows."""
    values = {"user_id": user_id, "staff_id": staff_id or 0, "staff_type": staff_type or ""}
    user_row = db.execute(text("SELECT full_name, email, username FROM users WHERE id = :user_id"), values).mappings().first()
    names = []
    emails = []
    usernames = []
    if user_row:
        for key in ("full_name",):
            if user_row.get(key):
                names.append(str(user_row[key]).strip())
        if user_row.get("email"):
            emails.append(str(user_row["email"]).strip())
        if user_row.get("username"):
            usernames.append(str(user_row["username"]).strip())

    if staff_type in ("employee", "manager") and staff_id:
        table = "employee_users" if staff_type == "employee" else "manager_users"
        cols = _table_columns(db, table)
        select_cols = [c for c in ("name", "surname", "employee_number", "manager_code") if c in cols]
        if select_cols:
            row = db.execute(text(f"SELECT {', '.join(select_cols)} FROM {table} WHERE id = :staff_id"), values).mappings().first()
            if row:
                first = str(row.get("name") or "").strip()
                last = str(row.get("surname") or "").strip()
                full = (first + " " + last).strip()
                if full:
                    names.append(full)
                if first:
                    names.append(first)
                if last:
                    names.append(last)
                for code_col in ("employee_number", "manager_code"):
                    if row.get(code_col):
                        usernames.append(str(row[code_col]).strip())

    # Keep only useful, distinct text snippets so broad words like just a first name do not remove unrelated records.
    distinct_names = []
    for val in names:
        if val and len(val) >= 3 and val.lower() not in {v.lower() for v in distinct_names}:
            distinct_names.append(val)
    values["full_name"] = distinct_names[0] if distinct_names else ""
    values["email"] = emails[0] if emails else ""
    values["username"] = usernames[0] if usernames else ""
    return values


def _cleanup_notifications_for_removed_user(db: Session, identity: dict) -> int:
    """Remove latest/outbox notifications for a deleted user after source rows are deleted.

    Older installs sometimes saved notifications without user_id/recipient_user_id and only kept
    the staff name/email in subject/message. This cleanup catches both linked and denormalized
    notifications, plus notifications whose source attendance/leave/IRP5 row no longer exists.
    """
    if not _table_exists(db, "notifications"):
        return 0
    params = dict(identity)
    result = db.execute(text("""
        DELETE FROM notifications n
        WHERE n.user_id = :user_id
           OR n.recipient_user_id = :user_id
           OR (n.franchise_user_id = :staff_id AND :staff_type = 'franchise')
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

def _delete_user_related_records(db: Session, user_id: int, staff_type: str | None = None, staff_id: int | None = None) -> dict:
    """Delete records that make a removed user appear anywhere in the system.

    This is used by SuperUser deactivation for Admin/Franchise/Manager/Employee accounts.
    It removes data shown on Overview, History, Approvals, HR Staff, Leave, Payroll, IRP5,
    and latest/outbox notifications. Column checks keep older databases safe.
    """
    deleted = {
        "overview": 0, "history": 0, "approvals": 0, "hr_staff": 0,
        "leave": 0, "payroll": 0, "irp5": 0, "notifications": 0,
    }
    params = _user_identity_values(db, user_id, staff_type, staff_id)

    if _table_exists(db, "attendance_events"):
        result = db.execute(text("DELETE FROM attendance_events WHERE user_id = :user_id"), params)
        count = result.rowcount or 0
        deleted["history"] += count
        deleted["approvals"] += count
        deleted["overview"] += count

    if _table_exists(db, "notifications"):
        result = db.execute(text("""
            DELETE FROM notifications
            WHERE user_id = :user_id
               OR recipient_user_id = :user_id
               OR (franchise_user_id = :staff_id AND :staff_type = 'franchise')
        """), params)
        count = result.rowcount or 0
        deleted["notifications"] += count
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
            count = result.rowcount or 0
            deleted["leave"] += count
            deleted["overview"] += count


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
        if "target_staff_type" in irp5_cols and "target_staff_id" in irp5_cols and staff_type:
            conditions.append("(target_staff_type = :staff_type AND target_staff_id = :staff_id)")
        if conditions:
            result = db.execute(text("DELETE FROM irp5_documents WHERE " + " OR ".join(conditions)), params)
            deleted["irp5"] += result.rowcount or 0

    if _table_exists(db, "gps_allocations_per_user"):
        result = db.execute(text("DELETE FROM gps_allocations_per_user WHERE user_id = :user_id"), params)
        deleted["overview"] += result.rowcount or 0

    final_notification_cleanup = _cleanup_notifications_for_removed_user(db, params)
    deleted["notifications"] += final_notification_cleanup
    deleted["overview"] += final_notification_cleanup

    return deleted


def _cleanup_franchise_user(db: Session, franchise_id: int, now: datetime) -> dict:
    """Deactivate a franchise user's staff and remove all tab-visible franchise data."""
    totals = {"overview": 0, "history": 0, "approvals": 0, "hr_staff": 0, "leave": 0, "payroll": 0, "irp5": 0, "notifications": 0}

    staff_rows = []
    if _table_exists(db, "manager_users"):
        staff_rows += [("manager", r["id"], r["user_id"]) for r in db.execute(text("SELECT id, user_id FROM manager_users WHERE franchise_user_id = :fid"), {"fid": franchise_id}).mappings().all()]
    if _table_exists(db, "employee_users"):
        staff_rows += [("employee", r["id"], r["user_id"]) for r in db.execute(text("SELECT id, user_id FROM employee_users WHERE franchise_user_id = :fid"), {"fid": franchise_id}).mappings().all()]

    for staff_type, staff_id, staff_user_id in staff_rows:
        cleaned = _delete_user_related_records(db, staff_user_id, staff_type, staff_id)
        for key, value in cleaned.items():
            totals[key] = totals.get(key, 0) + value
        db.execute(text("UPDATE users SET is_active = FALSE, updated_at = :now WHERE id = :user_id"), {"user_id": staff_user_id, "now": now})
        table = "manager_users" if staff_type == "manager" else "employee_users"
        db.execute(text(f"UPDATE {table} SET is_active = FALSE, updated_at = :now WHERE id = :staff_id"), {"staff_id": staff_id, "now": now})
        totals["hr_staff"] += 1

    if _table_exists(db, "notifications"):
        result = db.execute(text("DELETE FROM notifications WHERE franchise_user_id = :fid"), {"fid": franchise_id})
        count = result.rowcount or 0
        totals["notifications"] += count
        totals["overview"] += count

    return totals



@router.get("")
def list_users(
    role: str | None = None,
    is_active: bool | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superuser(db, current_user)

    sql = """
        SELECT
            u.id,
            u.full_name,
            u.email,
            u.is_active,
            CASE WHEN LOWER(COALESCE(u.email, '')) = 'wjm@martinsdirect.com' THEN TRUE ELSE FALSE END AS is_protected,
            STRING_AGG(r.name, ', ' ORDER BY r.name) AS roles
        FROM users u
        LEFT JOIN user_roles ur ON ur.user_id = u.id
        LEFT JOIN roles r ON r.id = ur.role_id
        WHERE 1 = 1
    """
    params = {}

    if role:
        sql += """
            AND EXISTS (
                SELECT 1
                FROM user_roles ur2
                JOIN roles r2 ON r2.id = ur2.role_id
                WHERE ur2.user_id = u.id
                AND r2.name = :role
            )
        """
        params["role"] = role

    if is_active is not None:
        sql += " AND u.is_active = :is_active"
        params["is_active"] = is_active

    sql += " GROUP BY u.id, u.full_name, u.email, u.is_active ORDER BY u.id DESC"

    rows = db.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


@router.post("/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    body: dict | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superuser(db, current_user)

    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own SuperUser account")

    user = db.execute(text("SELECT id, email FROM users WHERE id = :id"), {"id": user_id}).mappings().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if (user.get("email") or "").strip().lower() == PROTECTED_SUPERUSER_EMAIL:
        raise HTTPException(status_code=403, detail="The protected Martinsdirect SuperUser cannot be edited, deactivated, or deleted")

    now = datetime.utcnow()

    related_deleted = {
        "overview": 0, "history": 0, "approvals": 0, "hr_staff": 0,
        "leave": 0, "payroll": 0, "irp5": 0, "notifications": 0,
    }

    franchise_rows = []
    if _table_exists(db, "franchise_users"):
        franchise_rows = db.execute(text("SELECT id FROM franchise_users WHERE user_id = :id"), {"id": user_id}).mappings().all()
    for franchise_row in franchise_rows:
        cleaned = _cleanup_franchise_user(db, franchise_row["id"], now)
        for key, value in cleaned.items():
            related_deleted[key] = related_deleted.get(key, 0) + value

    manager_rows = []
    if _table_exists(db, "manager_users"):
        manager_rows = db.execute(text("SELECT id FROM manager_users WHERE user_id = :id"), {"id": user_id}).mappings().all()
    for manager_row in manager_rows:
        cleaned = _delete_user_related_records(db, user_id, "manager", manager_row["id"])
        for key, value in cleaned.items():
            related_deleted[key] = related_deleted.get(key, 0) + value
        related_deleted["hr_staff"] += 1

    employee_rows = []
    if _table_exists(db, "employee_users"):
        employee_rows = db.execute(text("SELECT id FROM employee_users WHERE user_id = :id"), {"id": user_id}).mappings().all()
    for employee_row in employee_rows:
        cleaned = _delete_user_related_records(db, user_id, "employee", employee_row["id"])
        for key, value in cleaned.items():
            related_deleted[key] = related_deleted.get(key, 0) + value
        related_deleted["hr_staff"] += 1

    cleaned = _delete_user_related_records(db, user_id)
    for key, value in cleaned.items():
        related_deleted[key] = related_deleted.get(key, 0) + value

    db.execute(text("""
        UPDATE users
        SET is_active = FALSE,
            updated_at = :updated_at
        WHERE id = :id
    """), {"id": user_id, "updated_at": now})

    db.execute(text("UPDATE franchise_users SET is_active = FALSE, updated_at = :updated_at WHERE user_id = :id"),
               {"id": user_id, "updated_at": now})
    db.execute(text("UPDATE manager_users SET is_active = FALSE, updated_at = :updated_at WHERE user_id = :id"),
               {"id": user_id, "updated_at": now})
    db.execute(text("UPDATE employee_users SET is_active = FALSE, updated_at = :updated_at WHERE user_id = :id"),
               {"id": user_id, "updated_at": now})

    db.commit()
    return {"message": "User deactivated system-wide and related data removed", "user_id": user_id, "related_deleted": related_deleted}


@router.post("/{user_id}/activate")
def activate_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superuser(db, current_user)

    user = db.execute(text("SELECT id FROM users WHERE id = :id"), {"id": user_id}).mappings().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.execute(text("""
        UPDATE users
        SET is_active = TRUE,
            updated_at = :updated_at
        WHERE id = :id
    """), {"id": user_id, "updated_at": datetime.utcnow()})

    db.execute(text("UPDATE franchise_users SET is_active = TRUE, updated_at = :updated_at WHERE user_id = :id"),
               {"id": user_id, "updated_at": datetime.utcnow()})
    db.execute(text("UPDATE manager_users SET is_active = TRUE, updated_at = :updated_at WHERE user_id = :id"),
               {"id": user_id, "updated_at": datetime.utcnow()})
    db.execute(text("UPDATE employee_users SET is_active = TRUE, updated_at = :updated_at WHERE user_id = :id"),
               {"id": user_id, "updated_at": datetime.utcnow()})

    db.commit()
    return {"message": "User activated system-wide", "user_id": user_id}
