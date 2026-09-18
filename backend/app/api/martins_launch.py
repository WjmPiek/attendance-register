"""Signed Martins System entry point for the Attendance application."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.models.core import FranchiseUser, Role, SuperUser, User, UserRole


router = APIRouter()


class MartinsLaunchRequest(BaseModel):
    token: str


class MartinsLaunchResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    main_app_url: str = ""


@router.post("/martins-launch", response_model=MartinsLaunchResponse)
def martins_launch(payload: MartinsLaunchRequest, db: Session = Depends(get_db)):
    """Exchange a short-lived signed Martins handoff for an Attendance JWT."""
    secret = getattr(settings, "ATTENDANCE_LAUNCH_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Attendance launch is not configured.",
        )

    serializer = URLSafeTimedSerializer(secret, salt="martins-attendance-launch-v1")
    try:
        handoff = serializer.loads(payload.token, max_age=120)
    except SignatureExpired as exc:
        raise HTTPException(status_code=401, detail="Attendance launch has expired.") from exc
    except BadSignature as exc:
        raise HTTPException(status_code=401, detail="Attendance launch is invalid.") from exc

    if handoff.get("module") != "attendance" or not handoff.get("email"):
        raise HTTPException(status_code=401, detail="Attendance launch is invalid.")

    user = (
        db.query(User)
        .filter(func.lower(User.email) == str(handoff["email"]).strip().lower())
        .first()
    )
    is_admin = bool(handoff.get("is_admin"))
    franchises = [str(item).strip() for item in handoff.get("franchises", []) if str(item).strip()]
    if not is_admin and not franchises:
        raise HTTPException(
            status_code=403,
            detail="Your Martins account does not have an assigned franchise.",
        )

    # The signed handoff is issued only after the Martins module-activation
    # check.  It is therefore the source of truth for first-time access: create
    # or reactivate the matching Attendance identity instead of asking the user
    # to maintain a second login and password.
    if not user:
        user = User(
            full_name=str(handoff.get("name") or handoff["email"]).strip(),
            email=str(handoff["email"]).strip().lower(),
            password_hash=hash_password(secrets.token_urlsafe(32)),
            is_active=True,
        )
        db.add(user)
        db.flush()
    else:
        user.full_name = str(handoff.get("name") or user.full_name or user.email).strip()
        user.is_active = True

    role_name = "SuperUser" if is_admin else "FranchiseUser"
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        role = Role(name=role_name, description=f"{role_name} access")
        db.add(role)
        db.flush()
    if not db.query(UserRole).filter(
        UserRole.user_id == user.id, UserRole.role_id == role.id
    ).first():
        db.add(UserRole(user_id=user.id, role_id=role.id))

    if is_admin:
        if not db.query(SuperUser).filter(SuperUser.user_id == user.id).first():
            db.add(SuperUser(user_id=user.id, notes="Linked from Martins System"))
    else:
        profile = db.query(FranchiseUser).filter(FranchiseUser.user_id == user.id).first()
        if not profile:
            profile = FranchiseUser(user_id=user.id)
            db.add(profile)
        profile.franchise_name = franchises[0]
        profile.business_name = franchises[0]
        profile.is_active = True

    db.commit()
    db.refresh(user)

    token = create_access_token(str(user.id))
    return MartinsLaunchResponse(
        access_token=token,
        main_app_url=str(handoff.get("return_url") or getattr(settings, "MARTINS_MAIN_APP_URL", "")),
    )
