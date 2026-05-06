from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models.core import Role, User, UserRole
from app.schemas.user import CreateUserRequest, UserListItem

router = APIRouter()


@router.get("", response_model=list[UserListItem])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("SuperUser", "FranchiseUser", "ManagerUser")),
):
    users = db.query(User).order_by(User.id).all()
    result = []
    for user in users:
        role_names = [ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]
        result.append(UserListItem(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            is_active=user.is_active,
            roles=role_names,
        ))
    return result


@router.post("", response_model=UserListItem)
def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("SuperUser")),
):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.flush()

    for role_name in payload.roles:
        role = db.query(Role).filter(Role.name == role_name).first()
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id))

    db.commit()
    db.refresh(user)
    return UserListItem(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        is_active=user.is_active,
        roles=payload.roles,
    )
