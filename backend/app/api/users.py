from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models.core import Role, User, UserRole
from app.schemas.user import CreateUserRequest, UserListItem

router = APIRouter()


@router.post("", response_model=UserListItem)
def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("SuperUser")),
):
    profile_roles = {"SuperUser", "FranchiseUser", "ManagerUser", "EmployeeUser"}
    invalid_roles = profile_roles.intersection(payload.roles)
    if invalid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Organisational users must be created through their dedicated "
                f"profile workflow: {', '.join(sorted(invalid_roles))}"
            ),
        )
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

    assigned_roles = []
    for role_name in payload.roles:
        role = db.query(Role).filter(Role.name == role_name).first()
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id))
            assigned_roles.append(role.name)

    db.commit()
    db.refresh(user)
    return UserListItem(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        is_active=user.is_active,
        roles=assigned_roles,
    )
