from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timedelta
import hashlib, os, secrets
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.core import Role, SuperUser, User, UserRole
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.services.email_service import send_smtp_email

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
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email.ilike(email), User.is_active == True).first()
    if not user:
        row = db.execute(text("""
            SELECT u.id
            FROM users u
            LEFT JOIN employee_users e ON e.user_id=u.id
            LEFT JOIN manager_users m ON m.user_id=u.id
            LEFT JOIN franchise_users f ON f.user_id=u.id
            WHERE COALESCE(u.is_active,TRUE)=TRUE
              AND LOWER(COALESCE(NULLIF(u.email,''),NULLIF(e.email,''),NULLIF(m.email,''),NULLIF(f.email,'')))=:email
            LIMIT 1
        """), {"email": email}).mappings().first()
        if row:
            user = db.query(User).filter(User.id == row["id"]).first()
    generic = {"message": "If the account exists, a password reset email has been sent."}
    if not user:
        return generic
    delivery_email = db.execute(text("""
        SELECT COALESCE(NULLIF(u.email,''),NULLIF(e.email,''),NULLIF(m.email,''),NULLIF(f.email,''))
        FROM users u
        LEFT JOIN employee_users e ON e.user_id=u.id
        LEFT JOIN manager_users m ON m.user_id=u.id
        LEFT JOIN franchise_users f ON f.user_id=u.id
        WHERE u.id=:uid
    """), {"uid": user.id}).scalar()
    if not delivery_email:
        return generic
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires = datetime.utcnow() + timedelta(minutes=60)
    db.execute(text("UPDATE password_reset_tokens SET used_at=NOW() WHERE user_id=:uid AND used_at IS NULL"), {"uid": user.id})
    db.execute(text("INSERT INTO password_reset_tokens(user_id,token_hash,expires_at,created_at) VALUES(:uid,:hash,:expires,NOW())"), {"uid":user.id,"hash":token_hash,"expires":expires})
    db.commit()
    frontend = os.getenv("FRONTEND_URL", "").rstrip('/')
    reset_url = f"{frontend}/?reset_token={raw_token}" if frontend else f"/?reset_token={raw_token}"
    state, sent_at, error, _ = send_smtp_email(delivery_email, "Reset your Attendance Register password", f"Hello {user.full_name or 'User'},\n\nUse this secure link within 60 minutes to create a new password:\n{reset_url}\n\nIf you did not request this, ignore this email.")
    if state != "sent":
        raise HTTPException(status_code=503, detail=f"Password reset email could not be sent: {error or 'SMTP is not configured'}")
    return generic

class ResetForgottenPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)

@router.post("/reset-password")
def reset_forgotten_password(payload: ResetForgottenPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    row = db.execute(text("SELECT id,user_id FROM password_reset_tokens WHERE token_hash=:hash AND used_at IS NULL AND expires_at>NOW() ORDER BY id DESC LIMIT 1"), {"hash":token_hash}).mappings().first()
    if not row:
        raise HTTPException(status_code=400, detail="This reset link is invalid or expired")
    db.execute(text("UPDATE users SET password_hash=:password, updated_at=NOW() WHERE id=:uid"), {"password":hash_password(payload.password),"uid":row["user_id"]})
    db.execute(text("UPDATE password_reset_tokens SET used_at=NOW() WHERE id=:id"), {"id":row["id"]})
    db.commit()
    return {"message":"Password changed successfully. You can now sign in."}


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
