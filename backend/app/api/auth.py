from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.core import Role, SuperUser, User, UserRole
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    login_value = (payload.email or "").strip()
    user = db.query(User).filter(or_(User.email == login_value, User.username == login_value)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


class SetupAdminRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str


@router.post("/setup-admin")
def setup_admin(payload: SetupAdminRequest, db: Session = Depends(get_db)):
    """Create the first real SuperUser/admin for a fresh production database.

    This endpoint is intentionally limited to a fresh install. It is allowed only
    when the database is empty or contains only the default demo seed accounts
    created by seed_initial_data(). After a real user exists, it returns 403.
    """
    seed_emails = {"admin@example.com", "employee@example.com"}
    existing_users = db.query(User).all()
    real_users = [u for u in existing_users if (u.email or "").lower() not in seed_emails]
    if real_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Initial admin setup is already locked because a real user exists.",
        )

    email = str(payload.email).strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")
    if len(payload.password or "") < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters")

    user = db.query(User).filter(User.email == email).first()
    if user:
        user.full_name = payload.full_name.strip() or user.full_name
        user.password_hash = hash_password(payload.password)
        user.is_active = True
    else:
        user = User(
            full_name=payload.full_name.strip() or "System Administrator",
            email=email,
            password_hash=hash_password(payload.password),
            is_active=True,
        )
        db.add(user)
        db.flush()

    super_role = db.query(Role).filter(Role.name == "SuperUser").first()
    if not super_role:
        super_role = Role(name="SuperUser", description="Full system access")
        db.add(super_role)
        db.flush()

    existing_role = db.query(UserRole).filter(UserRole.user_id == user.id, UserRole.role_id == super_role.id).first()
    if not existing_role:
        db.add(UserRole(user_id=user.id, role_id=super_role.id))

    existing_super = db.query(SuperUser).filter(SuperUser.user_id == user.id).first()
    if not existing_super:
        db.add(SuperUser(user_id=user.id, notes="Production setup admin"))

    db.commit()
    return {
        "message": "Admin user created. This setup endpoint is now locked for future use.",
        "email": email,
        "login_endpoint": "/api/auth/login",
    }


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == str(payload.email)).first()
    if not user:
        return {
            "message": "If this email exists, a password reset can be done by the responsible administrator.",
            "reset_path": "Ask your FranchiseUser or SuperUser to open HR Staff, select the staff member, and use Reset Password.",
        }
    manager = db.execute(text("""
        SELECT mu.franchise_user_id, fu.email AS franchise_email, fu.franchisee_name, fu.franchisee_surname
        FROM manager_users mu
        LEFT JOIN franchise_users fu ON fu.id = mu.franchise_user_id
        WHERE mu.user_id = :user_id
        LIMIT 1
    """), {"user_id": user.id}).mappings().first()
    employee = db.execute(text("""
        SELECT eu.franchise_user_id, fu.email AS franchise_email, fu.franchisee_name, fu.franchisee_surname
        FROM employee_users eu
        LEFT JOIN franchise_users fu ON fu.id = eu.franchise_user_id
        WHERE eu.user_id = :user_id
        LIMIT 1
    """), {"user_id": user.id}).mappings().first()
    owner = manager or employee
    if owner:
        admin_name = f"{owner.get('franchisee_name') or ''} {owner.get('franchisee_surname') or ''}".strip()
        return {
            "message": "Your FranchiseUser can reset this password from HR Staff > View/Edit > Reset Password.",
            "franchise_admin": admin_name or None,
            "franchise_admin_email": owner.get('franchise_email'),
            "reset_path": "HR Staff > View/Edit staff member > Reset Password",
        }
    return {
        "message": "Ask a SuperUser/admin to reset this password.",
        "reset_path": "SuperUser can reset the user password from staff/user management.",
    }


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles = [ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == current_user.id).all()]
    emp = db.execute(text("""
        SELECT employee_role, franchise_user_id
        FROM employee_users
        WHERE user_id = :uid
        LIMIT 1
    """), {"uid": current_user.id}).mappings().first()
    franchise = db.execute(text("""
        SELECT id AS franchise_user_id
        FROM franchise_users
        WHERE user_id = :uid
        LIMIT 1
    """), {"uid": current_user.id}).mappings().first()
    return CurrentUserResponse(
        id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        username=getattr(current_user, "username", None),
        roles=roles,
        employee_role=emp.get('employee_role') if emp else None,
        franchise_user_id=(emp.get('franchise_user_id') if emp else (franchise.get('franchise_user_id') if franchise else None)),
    )
