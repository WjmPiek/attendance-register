from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import hash_password
from app.db.session import get_db
from app.models.core import FranchiseRegistration, FranchiseUser, Role, User, UserRole
from app.services.audit import write_audit_log
from app.schemas.franchise import (
    FranchiseRegistrationCreate,
    FranchiseRegistrationDecision,
    FranchiseRegistrationResponse,
)

router = APIRouter()


def _ensure_franchise_website_schema(db: Session):
    """Keep older databases compatible with franchise website edits/register.

    Safe to run repeatedly. It only adds missing columns.
    """
    db.execute(text("ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS website VARCHAR(500) NULL"))
    db.execute(text("ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL"))
    db.execute(text("ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(500) NULL"))
    db.execute(text("ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL"))
    db.commit()


def _role_names(db: Session, user_id: int) -> list[str]:
    return [ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user_id).all()]


def _require_superuser(db: Session, user: User):
    if "SuperUser" not in _role_names(db, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only SuperUser can review franchise registrations")


@router.post("/register", response_model=FranchiseRegistrationResponse)
def register_franchise(payload: FranchiseRegistrationCreate, db: Session = Depends(get_db)):
    _ensure_franchise_website_schema(db)
    existing_user = db.query(User).filter(User.email == payload.email).first()
    existing_registration = db.query(FranchiseRegistration).filter(FranchiseRegistration.email == payload.email).first()
    if existing_user or existing_registration:
        raise HTTPException(status_code=400, detail="A user or registration with this email already exists")

    registration = FranchiseRegistration(
        business_name=payload.business_name,
        trading_as=payload.trading_as,
        business_registration_number=payload.business_registration_number,
        vat_number=payload.vat_number,
        office_address=payload.office_address,
        website=_normalise_website(payload.website),
        office_number=payload.office_number,
        twenty_four_hour_number=payload.twenty_four_hour_number,
        franchisee_name=payload.franchisee_name,
        franchisee_surname=payload.franchisee_surname,
        email=payload.email,
        contact_number=payload.contact_number,
        password_hash=hash_password(payload.password),
        status="pending",
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration


@router.get("/registrations", response_model=list[FranchiseRegistrationResponse])
def list_franchise_registrations(
    status_filter: str = "pending",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superuser(db, current_user)
    _ensure_franchise_website_schema(db)
    normalized_status = (status_filter or "pending").strip().lower()
    query = db.query(FranchiseRegistration)
    if normalized_status and normalized_status != "all":
        query = query.filter(FranchiseRegistration.status == normalized_status)
    return query.order_by(FranchiseRegistration.created_at.desc()).all()


@router.post("/registrations/{registration_id}/approve", response_model=FranchiseRegistrationResponse)
def approve_franchise_registration(
    registration_id: int,
    payload: FranchiseRegistrationDecision,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superuser(db, current_user)
    _ensure_franchise_website_schema(db)
    registration = db.query(FranchiseRegistration).filter(FranchiseRegistration.id == registration_id).first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")
    if registration.status == "approved":
        return registration

    existing_user = db.query(User).filter(User.email == registration.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="A user with this email already exists")

    user = User(
        full_name=f"{registration.franchisee_name} {registration.franchisee_surname}",
        email=registration.email,
        password_hash=registration.password_hash,
        is_active=True,
    )
    db.add(user)
    db.flush()

    role = db.query(Role).filter(Role.name == "FranchiseUser").first()
    if not role:
        raise HTTPException(status_code=500, detail="FranchiseUser role is missing")

    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add(FranchiseUser(
        user_id=user.id,
        franchise_name=registration.trading_as or registration.business_name,
        business_name=registration.business_name,
        trading_as=registration.trading_as,
        business_registration_number=registration.business_registration_number,
        vat_number=registration.vat_number,
        office_address=registration.office_address,
        website=_normalise_website(getattr(registration, "website", None)),
        office_number=registration.office_number,
        twenty_four_hour_number=registration.twenty_four_hour_number,
        contact_number=registration.contact_number,
        is_active=True,
    ))

    registration.status = "approved"
    registration.approved_by_user_id = current_user.id
    registration.approved_at = datetime.utcnow()
    registration.rejected_reason = None

    db.commit()
    db.refresh(registration)
    return registration


@router.post("/registrations/{registration_id}/reject", response_model=FranchiseRegistrationResponse)
def reject_franchise_registration(
    registration_id: int,
    payload: FranchiseRegistrationDecision,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superuser(db, current_user)
    registration = db.query(FranchiseRegistration).filter(FranchiseRegistration.id == registration_id).first()
    if not registration:
        raise HTTPException(status_code=404, detail="Registration not found")

    registration.status = "rejected"
    registration.rejected_reason = payload.note or "Rejected by SuperUser"
    registration.approved_by_user_id = current_user.id
    registration.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(registration)
    return registration


class FranchiseRegistrationUpdate(BaseModel):
    business_name: str | None = None
    trading_as: str | None = None
    business_registration_number: str | None = None
    business_registration: str | None = None
    vat_number: str | None = None
    vat_nr: str | None = None
    office_address: str | None = None
    website: str | None = None
    office_number: str | None = None
    twenty_four_hour_number: str | None = None
    franchisee_name: str | None = None
    franchisee_surname: str | None = None
    email: str | None = None
    contact_number: str | None = None
    contact: str | None = None


def _normalise_website(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    if not value.lower().startswith(("http://", "https://")):
        value = "https://" + value
    return value



def _safe_mapping(row):
    return dict(row) if row is not None else None

def _update_franchise_registration_and_profile(registration_id: int, payload: FranchiseRegistrationUpdate, current_user: User, db: Session):
    _require_superuser(db, current_user)
    _ensure_franchise_website_schema(db)

    existing = db.execute(text("SELECT * FROM franchise_registrations WHERE id = :id"), {"id": registration_id}).mappings().first()
    if not existing:
        raise HTTPException(status_code=404, detail="Registration not found")

    data = payload.model_dump(exclude_unset=True)
    # Accept both backend column names and common frontend field names.
    if "business_registration" in data and "business_registration_number" not in data:
        data["business_registration_number"] = data.pop("business_registration")
    else:
        data.pop("business_registration", None)
    if "vat_nr" in data and "vat_number" not in data:
        data["vat_number"] = data.pop("vat_nr")
    else:
        data.pop("vat_nr", None)
    if "contact" in data and "contact_number" not in data:
        data["contact_number"] = data.pop("contact")
    else:
        data.pop("contact", None)
    if "website" in data:
        data["website"] = _normalise_website(data.get("website"))
    if not data:
        return dict(existing)

    allowed = [
        "business_name", "trading_as", "business_registration_number", "vat_number",
        "office_address", "website", "office_number", "twenty_four_hour_number",
        "franchisee_name", "franchisee_surname", "email", "contact_number",
    ]
    sets = [f"{k} = :{k}" for k in allowed if k in data]
    params = {**data, "id": registration_id, "updated_at": datetime.utcnow()}
    updated = db.execute(text(f"""
        UPDATE franchise_registrations
        SET {', '.join(sets)}, updated_at = :updated_at
        WHERE id = :id
        RETURNING *
    """), params).mappings().first()

    # Always keep the live franchise profile in sync.
    # The admin screen and Staff ID QR code read from franchise_users.website,
    # so saving only franchise_registrations.website is not enough.
    if updated:
        live_sets = []
        live_params = {
            "email": updated.get("email"),
            "registration_id": registration_id,
            "updated_at": datetime.utcnow(),
        }
        mapping = {
            "business_name": "business_name",
            "trading_as": "trading_as",
            "business_registration_number": "business_registration_number",
            "vat_number": "vat_number",
            "office_address": "office_address",
            "website": "website",
            "office_number": "office_number",
            "twenty_four_hour_number": "twenty_four_hour_number",
            "contact_number": "contact_number",
        }
        for source, target in mapping.items():
            if source in data:
                live_sets.append(f"{target} = :{source}")
                live_params[source] = data[source]
        if "business_name" in data or "trading_as" in data:
            live_sets.append("franchise_name = COALESCE(:trading_as_for_name, :business_name_for_name, franchise_name)")
            live_params["trading_as_for_name"] = updated.get("trading_as")
            live_params["business_name_for_name"] = updated.get("business_name")

        if live_sets:
            db.execute(text(f"""
                UPDATE franchise_users fu
                SET {', '.join(live_sets)}, updated_at = :updated_at
                FROM users u
                WHERE u.id = fu.user_id
                  AND LOWER(u.email) = LOWER(:email)
            """), live_params)

    write_audit_log(db, actor_user_id=current_user.id, action="update", entity_type="franchise_registration", entity_id=registration_id, old_values=_safe_mapping(existing), new_values=dict(updated) if updated else data, note="Franchise registration edited")
    db.commit()
    return dict(updated) if updated else {"id": registration_id}


class FranchiseLiveProfileUpdate(BaseModel):
    franchise_name: str | None = None
    business_name: str | None = None
    trading_as: str | None = None
    business_registration_number: str | None = None
    business_registration: str | None = None
    vat_number: str | None = None
    vat_nr: str | None = None
    office_address: str | None = None
    website: str | None = None
    office_number: str | None = None
    twenty_four_hour_number: str | None = None
    contact_number: str | None = None
    contact: str | None = None


def _update_live_franchise_profile(franchise_user_id: int, payload: FranchiseLiveProfileUpdate, current_user: User, db: Session):
    _require_superuser(db, current_user)
    _ensure_franchise_website_schema(db)

    existing = db.execute(text("SELECT * FROM franchise_users WHERE id = :id"), {"id": franchise_user_id}).mappings().first()
    if not existing:
        raise HTTPException(status_code=404, detail="Franchise profile not found")

    data = payload.model_dump(exclude_unset=True)
    # Accept both backend column names and common frontend field names.
    if "business_registration" in data and "business_registration_number" not in data:
        data["business_registration_number"] = data.pop("business_registration")
    else:
        data.pop("business_registration", None)
    if "vat_nr" in data and "vat_number" not in data:
        data["vat_number"] = data.pop("vat_nr")
    else:
        data.pop("vat_nr", None)
    if "contact" in data and "contact_number" not in data:
        data["contact_number"] = data.pop("contact")
    else:
        data.pop("contact", None)
    if "website" in data:
        data["website"] = _normalise_website(data.get("website"))
    if not data:
        return dict(existing)

    allowed = [
        "franchise_name", "business_name", "trading_as", "business_registration_number",
        "vat_number", "office_address", "website", "office_number",
        "twenty_four_hour_number", "contact_number",
    ]
    sets = [f"{k} = :{k}" for k in allowed if k in data]
    params = {**data, "id": franchise_user_id, "updated_at": datetime.utcnow()}
    updated = db.execute(text(f"""
        UPDATE franchise_users
        SET {', '.join(sets)}, updated_at = :updated_at
        WHERE id = :id
        RETURNING *
    """), params).mappings().first()

    # Also sync the matching registration record by the linked user's email when possible.
    if updated:
        user_email = db.execute(text("""
            SELECT u.email
            FROM users u
            JOIN franchise_users fu ON fu.user_id = u.id
            WHERE fu.id = :id
            LIMIT 1
        """), {"id": franchise_user_id}).scalar()
        if user_email:
            reg_sets = [f"{k} = :{k}" for k in [
                "business_name", "trading_as", "business_registration_number", "vat_number",
                "office_address", "website", "office_number", "twenty_four_hour_number", "contact_number"
            ] if k in data]
            if reg_sets:
                db.execute(text(f"""
                    UPDATE franchise_registrations
                    SET {', '.join(reg_sets)}, updated_at = :updated_at
                    WHERE LOWER(email) = LOWER(:email)
                """), {**data, "email": user_email, "updated_at": datetime.utcnow()})

    write_audit_log(db, actor_user_id=current_user.id, action="update", entity_type="franchise_profile", entity_id=franchise_user_id, franchise_user_id=franchise_user_id, old_values=_safe_mapping(existing), new_values=dict(updated) if updated else data, note="Live franchise profile edited")
    db.commit()
    return dict(updated) if updated else {"id": franchise_user_id}


@router.put("/franchise-users/{franchise_user_id}")
def update_live_franchise_user(franchise_user_id: int, payload: FranchiseLiveProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_live_franchise_profile(franchise_user_id, payload, current_user, db)


@router.patch("/franchise-users/{franchise_user_id}")
def patch_live_franchise_user(franchise_user_id: int, payload: FranchiseLiveProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_live_franchise_profile(franchise_user_id, payload, current_user, db)


@router.put("/users/{franchise_user_id}")
def update_live_franchise_user_short(franchise_user_id: int, payload: FranchiseLiveProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_live_franchise_profile(franchise_user_id, payload, current_user, db)


@router.patch("/users/{franchise_user_id}")
def patch_live_franchise_user_short(franchise_user_id: int, payload: FranchiseLiveProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_live_franchise_profile(franchise_user_id, payload, current_user, db)


@router.put("/registrations/{registration_id}")
def update_franchise_registration(registration_id: int, payload: FranchiseRegistrationUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_franchise_registration_and_profile(registration_id, payload, current_user, db)


@router.post("/registrations/{registration_id}/edit")
def edit_franchise_registration_post(registration_id: int, payload: FranchiseRegistrationUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_franchise_registration_and_profile(registration_id, payload, current_user, db)


@router.put("/registrations/{registration_id}/edit")
def edit_franchise_registration_put(registration_id: int, payload: FranchiseRegistrationUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_franchise_registration_and_profile(registration_id, payload, current_user, db)


@router.patch("/registrations/{registration_id}")
def patch_franchise_registration(registration_id: int, payload: FranchiseRegistrationUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_franchise_registration_and_profile(registration_id, payload, current_user, db)


@router.patch("/registrations/{registration_id}/edit")
def patch_franchise_registration_edit(registration_id: int, payload: FranchiseRegistrationUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_franchise_registration_and_profile(registration_id, payload, current_user, db)

# -----------------------------------------------------------------------------
# Live franchise profile edit endpoints
# SuperUser may edit any franchise profile.
# FranchiseUser may edit only the franchise profile linked to their own user_id.
# These endpoints update franchise_users.website, which is the value used by Staff ID QR codes.
# -----------------------------------------------------------------------------
class FranchiseUserUpdate(BaseModel):
    business_name: str | None = None
    trading_as: str | None = None
    franchise_name: str | None = None
    business_registration_number: str | None = None
    business_registration: str | None = None
    vat_number: str | None = None
    vat_nr: str | None = None
    office_address: str | None = None
    website: str | None = None
    office_number: str | None = None
    twenty_four_hour_number: str | None = None
    contact_number: str | None = None
    contact: str | None = None


def _is_superuser(db: Session, user: User) -> bool:
    return "SuperUser" in _role_names(db, user.id)


def _is_franchise_user(db: Session, user: User) -> bool:
    return "FranchiseUser" in _role_names(db, user.id)


def _normalise_franchise_user_payload(payload: FranchiseUserUpdate) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if "business_registration" in data and "business_registration_number" not in data:
        data["business_registration_number"] = data.pop("business_registration")
    else:
        data.pop("business_registration", None)
    if "vat_nr" in data and "vat_number" not in data:
        data["vat_number"] = data.pop("vat_nr")
    else:
        data.pop("vat_nr", None)
    if "contact" in data and "contact_number" not in data:
        data["contact_number"] = data.pop("contact")
    else:
        data.pop("contact", None)
    if "website" in data:
        data["website"] = _normalise_website(data.get("website"))
    if "trading_as" in data and "franchise_name" not in data:
        data["franchise_name"] = data.get("trading_as")
    return data


def _franchise_user_select_sql(where_sql: str) -> str:
    return f"""
        SELECT
            fu.id,
            fu.user_id,
            fu.franchise_name,
            fu.business_name,
            fu.trading_as,
            fu.business_registration_number,
            fu.vat_number,
            fu.office_address,
            fu.website,
            fu.office_number,
            fu.twenty_four_hour_number,
            fu.contact_number,
            fu.is_active,
            u.email,
            u.username,
            u.full_name,
            u.is_active AS login_active
        FROM franchise_users fu
        LEFT JOIN users u ON u.id = fu.user_id
        WHERE {where_sql}
    """


def _require_franchise_profile_access(db: Session, current_user: User, franchise_user_id: int | None = None):
    if _is_superuser(db, current_user):
        return
    if not _is_franchise_user(db, current_user):
        raise HTTPException(status_code=403, detail="Only SuperUser or FranchiseUser can edit franchise details")
    if franchise_user_id is None:
        return
    own = db.execute(text("SELECT id FROM franchise_users WHERE id = :fid AND user_id = :uid LIMIT 1"), {
        "fid": franchise_user_id,
        "uid": current_user.id,
    }).mappings().first()
    if not own:
        raise HTTPException(status_code=403, detail="You can only edit your own franchise details")


def _update_live_franchise_user(franchise_user_id: int, payload: FranchiseUserUpdate, current_user: User, db: Session):
    _ensure_franchise_website_schema(db)
    _require_franchise_profile_access(db, current_user, franchise_user_id)
    existing = db.execute(text(_franchise_user_select_sql("fu.id = :fid") + " LIMIT 1"), {"fid": franchise_user_id}).mappings().first()
    if not existing:
        raise HTTPException(status_code=404, detail="Franchise user not found")

    data = _normalise_franchise_user_payload(payload)
    previous_office_address = str(existing.get("office_address") or "").strip()
    new_office_address = str(data.get("office_address") or previous_office_address).strip()
    allowed = [
        "franchise_name", "business_name", "trading_as", "business_registration_number", "vat_number",
        "office_address", "website", "office_number", "twenty_four_hour_number", "contact_number",
    ]
    data = {k: v for k, v in data.items() if k in allowed}
    if not data:
        return dict(existing)

    sets = [f"{k} = :{k}" for k in data.keys()]
    params = {**data, "fid": franchise_user_id, "updated_at": datetime.utcnow()}
    updated = db.execute(text(f"""
        UPDATE franchise_users
        SET {', '.join(sets)}, updated_at = :updated_at
        WHERE id = :fid
        RETURNING *
    """), params).mappings().first()

    # When the franchise business address changes, update every linked record that still
    # points to the previous address. Staff who were deliberately assigned elsewhere are untouched.
    if updated and "office_address" in data and previous_office_address and new_office_address and previous_office_address.lower() != new_office_address.lower():
        sync_params = {"fid": franchise_user_id, "old_address": previous_office_address, "new_address": new_office_address, "updated_at": datetime.utcnow()}
        for table_name in ("employee_users", "manager_users"):
            db.execute(text(f"""
                UPDATE {table_name}
                SET office_address_assigned = :new_address, updated_at = :updated_at
                WHERE franchise_user_id = :fid
                  AND LOWER(TRIM(COALESCE(office_address_assigned, ''))) = LOWER(TRIM(:old_address))
            """), sync_params)
        db.execute(text("""
            UPDATE areas
            SET description = :new_address, office_address = :new_address, updated_at = :updated_at
            WHERE franchise_user_id = :fid
              AND (LOWER(TRIM(COALESCE(office_address, ''))) = LOWER(TRIM(:old_address))
                   OR LOWER(TRIM(COALESCE(description, ''))) = LOWER(TRIM(:old_address)))
        """), sync_params)

    # Keep matching approved registration in sync too, when the email links both records.
    if updated:
        user_email = db.execute(text("SELECT email FROM users WHERE id = :uid"), {"uid": updated.get("user_id")}).scalar()
        if user_email:
            reg_sets = []
            reg_params = {"email": user_email, "updated_at": datetime.utcnow()}
            for source in [
                "business_name", "trading_as", "business_registration_number", "vat_number",
                "office_address", "website", "office_number", "twenty_four_hour_number", "contact_number",
            ]:
                if source in data:
                    reg_sets.append(f"{source} = :{source}")
                    reg_params[source] = data[source]
            if reg_sets:
                db.execute(text(f"""
                    UPDATE franchise_registrations
                    SET {', '.join(reg_sets)}, updated_at = :updated_at
                    WHERE LOWER(email) = LOWER(:email)
                """), reg_params)

    db.commit()
    refreshed = db.execute(text(_franchise_user_select_sql("fu.id = :fid") + " LIMIT 1"), {"fid": franchise_user_id}).mappings().first()
    return dict(refreshed) if refreshed else dict(updated)


@router.get("/users")
def list_franchise_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_franchise_website_schema(db)
    if _is_superuser(db, current_user):
        rows = db.execute(text(_franchise_user_select_sql("1=1") + " ORDER BY fu.id DESC")).mappings().all()
        return {"items": [dict(r) for r in rows]}
    if _is_franchise_user(db, current_user):
        rows = db.execute(text(_franchise_user_select_sql("fu.user_id = :uid") + " ORDER BY fu.id DESC"), {"uid": current_user.id}).mappings().all()
        return {"items": [dict(r) for r in rows]}
    raise HTTPException(status_code=403, detail="Not allowed")


@router.get("/me")
def get_my_franchise_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_franchise_website_schema(db)
    _require_franchise_profile_access(db, current_user)
    row = db.execute(text(_franchise_user_select_sql("fu.user_id = :uid") + " LIMIT 1"), {"uid": current_user.id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Franchise profile not found")
    return dict(row)


@router.put("/users/{franchise_user_id}")
def update_franchise_user_put(franchise_user_id: int, payload: FranchiseUserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_live_franchise_user(franchise_user_id, payload, current_user, db)


@router.patch("/users/{franchise_user_id}")
def update_franchise_user_patch(franchise_user_id: int, payload: FranchiseUserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_live_franchise_user(franchise_user_id, payload, current_user, db)


@router.put("/me")
def update_my_franchise_profile_put(payload: FranchiseUserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_franchise_website_schema(db)
    row = db.execute(text("SELECT id FROM franchise_users WHERE user_id = :uid LIMIT 1"), {"uid": current_user.id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Franchise profile not found")
    return _update_live_franchise_user(row["id"], payload, current_user, db)


@router.patch("/me")
def update_my_franchise_profile_patch(payload: FranchiseUserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_franchise_website_schema(db)
    row = db.execute(text("SELECT id FROM franchise_users WHERE user_id = :uid LIMIT 1"), {"uid": current_user.id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Franchise profile not found")
    return _update_live_franchise_user(row["id"], payload, current_user, db)
