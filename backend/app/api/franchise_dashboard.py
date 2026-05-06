from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.core import User, UserRole

try:
    from app.core.security import get_password_hash
except Exception:
    get_password_hash = None

router = APIRouter()


def _roles(db: Session, user: User) -> list[str]:
    return [ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]


def _is_superuser(db: Session, user: User) -> bool:
    return "SuperUser" in _roles(db, user)


def _can_review(db: Session, user: User) -> bool:
    names = _roles(db, user)
    return any(r in names for r in ["SuperUser", "FranchiseUser", "ManagerUser"])


def _require_reviewer(db: Session, user: User):
    if not _can_review(db, user):
        raise HTTPException(status_code=403, detail="Approval access required")


def _hash_password(raw_password: str) -> str:
    if get_password_hash:
        return get_password_hash(raw_password)
    # Fallback only if your project security helper has a different name.
    # Replace this fallback with your existing password hashing helper if needed.
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(raw_password)


def _get_franchise_user_id_for_user(db: Session, user_id: int):
    row = db.execute(
        text("SELECT id FROM franchise_users WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().first()
    return row["id"] if row else None


@router.get("/dashboard")
def franchise_dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_reviewer(db, current_user)
    roles = _roles(db, current_user)
    franchise_user_id = _get_franchise_user_id_for_user(db, current_user.id)

    if "SuperUser" in roles:
        pending_franchise_sql = """
            SELECT *
            FROM franchise_registrations
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT 100
        """
        pending_attendance_sql = """
            SELECT *
            FROM attendance_events
            WHERE COALESCE(approval_status, 'pending') IN ('pending', 'pending_review')
            ORDER BY created_at DESC
            LIMIT 100
        """
        params = {}
    elif "FranchiseUser" in roles and franchise_user_id:
        pending_franchise_sql = """
            SELECT *
            FROM franchise_registrations
            WHERE 1 = 0
        """
        pending_attendance_sql = """
            SELECT ae.*
            FROM attendance_events ae
            JOIN employee_users eu ON eu.user_id = ae.user_id
            WHERE eu.franchise_user_id = :franchise_user_id
            AND COALESCE(ae.approval_status, 'pending') IN ('pending', 'pending_review')
            ORDER BY ae.created_at DESC
            LIMIT 100
        """
        params = {"franchise_user_id": franchise_user_id}
    else:
        pending_franchise_sql = "SELECT * FROM franchise_registrations WHERE 1 = 0"
        pending_attendance_sql = """
            SELECT ae.*
            FROM attendance_events ae
            JOIN employee_users eu ON eu.user_id = ae.user_id
            JOIN manager_users mu ON mu.id = eu.manager_user_id
            WHERE mu.user_id = :manager_user_id
            AND COALESCE(ae.approval_status, 'pending') IN ('pending', 'pending_review')
            ORDER BY ae.created_at DESC
            LIMIT 100
        """
        params = {"manager_user_id": current_user.id}

    pending_franchises = db.execute(text(pending_franchise_sql), params).mappings().all()
    pending_attendance = db.execute(text(pending_attendance_sql), params).mappings().all()

    return {
        "pending_franchises": [dict(x) for x in pending_franchises],
        "pending_attendance": [dict(x) for x in pending_attendance],
    }


@router.post("/registrations/{registration_id}/approve")
def approve_franchise_registration(
    registration_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _is_superuser(db, current_user):
        raise HTTPException(status_code=403, detail="Only SuperUser can approve franchise registrations")

    registration = db.execute(text("""
        SELECT *
        FROM franchise_registrations
        WHERE id = :id
    """), {"id": registration_id}).mappings().first()

    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")

    if registration["status"] == "approved":
        raise HTTPException(status_code=400, detail="Registration is already approved")

    existing_user = db.execute(text("""
        SELECT id
        FROM users
        WHERE email = :email
    """), {"email": registration["email"]}).mappings().first()

    if existing_user:
        raise HTTPException(status_code=400, detail="A user with this email already exists")

    password_hash = registration.get("password_hash")
    if not password_hash:
        raw_password = body.get("password")
        if not raw_password:
            raise HTTPException(
                status_code=400,
                detail="Registration has no password_hash. Send a password in approval body or update registration flow to store password_hash.",
            )
        password_hash = _hash_password(raw_password)

    full_name = f"{registration['franchisee_name']} {registration['franchisee_surname']}".strip()

    new_user_id = db.execute(text("""
        INSERT INTO users (full_name, email, password_hash, is_active, created_at, updated_at)
        VALUES (:full_name, :email, :password_hash, TRUE, :now, :now)
        RETURNING id
    """), {
        "full_name": full_name,
        "email": registration["email"],
        "password_hash": password_hash,
        "now": datetime.utcnow(),
    }).scalar_one()

    franchise_role = db.execute(text("""
        SELECT id
        FROM roles
        WHERE name = 'FranchiseUser'
    """)).mappings().first()

    if not franchise_role:
        raise HTTPException(status_code=500, detail="FranchiseUser role does not exist")

    db.execute(text("""
        INSERT INTO user_roles (user_id, role_id)
        VALUES (:user_id, :role_id)
        ON CONFLICT DO NOTHING
    """), {
        "user_id": new_user_id,
        "role_id": franchise_role["id"],
    })

    db.execute(text("""
        INSERT INTO franchise_users (
            user_id,
            franchise_name,
            business_name,
            trading_as,
            business_registration_number,
            vat_number,
            office_address,
            website,
            office_number,
            twenty_four_hour_number,
            contact_number,
            is_active,
            created_at,
            updated_at
        )
        VALUES (
            :user_id,
            :franchise_name,
            :business_name,
            :trading_as,
            :business_registration_number,
            :vat_number,
            :office_address,
            :website,
            :office_number,
            :twenty_four_hour_number,
            :contact_number,
            TRUE,
            :now,
            :now
        )
    """), {
        "user_id": new_user_id,
        "franchise_name": registration["business_name"],
        "business_name": registration["business_name"],
        "trading_as": registration.get("trading_as"),
        "business_registration_number": registration.get("business_registration_number"),
        "vat_number": registration.get("vat_number"),
        "office_address": registration.get("office_address"),
        "website": registration.get("website"),
        "office_number": registration.get("office_number"),
        "twenty_four_hour_number": registration.get("twenty_four_hour_number"),
        "contact_number": registration.get("contact_number"),
        "now": datetime.utcnow(),
    })

    db.execute(text("""
        UPDATE franchise_registrations
        SET status = 'approved',
            approved_by_user_id = :approved_by_user_id,
            approved_at = :approved_at,
            manager_note = :manager_note,
            rejected_reason = NULL,
            updated_at = :updated_at
        WHERE id = :id
    """), {
        "id": registration_id,
        "approved_by_user_id": current_user.id,
        "approved_at": datetime.utcnow(),
        "manager_note": body.get("manager_note"),
        "updated_at": datetime.utcnow(),
    })

    db.commit()

    return {
        "message": "Franchise approved and login user created",
        "registration_id": registration_id,
        "user_id": new_user_id,
    }


@router.post("/registrations/{registration_id}/reject")
def reject_franchise_registration(
    registration_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _is_superuser(db, current_user):
        raise HTTPException(status_code=403, detail="Only SuperUser can reject franchise registrations")

    reason = body.get("rejected_reason") or "Rejected"

    db.execute(text("""
        UPDATE franchise_registrations
        SET status = 'rejected',
            rejected_reason = :reason,
            manager_note = :manager_note,
            approved_by_user_id = :approved_by_user_id,
            approved_at = :approved_at,
            updated_at = :updated_at
        WHERE id = :id
    """), {
        "id": registration_id,
        "reason": reason,
        "manager_note": body.get("manager_note"),
        "approved_by_user_id": current_user.id,
        "approved_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    db.commit()

    return {"message": "Franchise registration rejected", "registration_id": registration_id}


@router.put("/registrations/{registration_id}")
def update_franchise_registration_details(registration_id: int, body: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _is_superuser(db, current_user):
        raise HTTPException(status_code=403, detail="Only SuperUser can edit franchise registrations")
    db.execute(text("ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS website VARCHAR(255) NULL"))
    db.execute(text("ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(255) NULL"))
    row = db.execute(text("SELECT * FROM franchise_registrations WHERE id = :id"), {"id": registration_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Registration not found")
    allowed = ["business_name","trading_as","business_registration_number","vat_number","office_address","website","office_number","twenty_four_hour_number","franchisee_name","franchisee_surname","email","contact_number"]
    data = {k: body.get(k) for k in allowed if k in body}
    if "website" in data and data["website"]:
        data["website"] = str(data["website"]).strip()
        if data["website"] and not data["website"].lower().startswith(("http://", "https://")):
            data["website"] = "https://" + data["website"]
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        row = db.execute(text(f"UPDATE franchise_registrations SET {sets}, updated_at = :updated_at WHERE id = :id RETURNING *"), {**data, "id": registration_id, "updated_at": datetime.utcnow()}).mappings().first()
        if row and str(row.get("status") or "").lower() == "approved":
            live = {k: data[k] for k in ["business_name","trading_as","business_registration_number","vat_number","office_address","website","office_number","twenty_four_hour_number","contact_number"] if k in data}
            if live:
                live_sets = ", ".join(f"{k} = :{k}" for k in live)
                db.execute(text(f"UPDATE franchise_users fu SET {live_sets}, updated_at = :updated_at FROM users u WHERE u.id = fu.user_id AND LOWER(u.email) = LOWER(:email)"), {**live, "email": row.get("email"), "updated_at": datetime.utcnow()})
    db.commit()
    return dict(row)

@router.post("/registrations/{registration_id}/edit")
def update_franchise_registration_details_post(registration_id: int, body: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return update_franchise_registration_details(registration_id, body, current_user, db)

@router.put("/registrations/{registration_id}/edit")
def update_franchise_registration_details_put(registration_id: int, body: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return update_franchise_registration_details(registration_id, body, current_user, db)
