from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.core import User, UserRole

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")
    return user


def require_roles(*allowed_roles: str):
    def _checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        role_names = {
            ur.role.name
            for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()
        }
        if allowed_roles and not role_names.intersection(set(allowed_roles)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _checker


def get_user_role_names(db: Session, user_id: int) -> set[str]:
    return {ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user_id).all()}


def user_has_role(db: Session, user: User, role_name: str) -> bool:
    return role_name in get_user_role_names(db, user.id)


def require_superuser(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if not user_has_role(db, user, "SuperUser"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SuperUser access required")
    return user


def get_current_franchise_user_id(db: Session, user: User) -> int:
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT id FROM franchise_users
        WHERE user_id = :user_id AND COALESCE(is_active, TRUE) = TRUE
    """), {"user_id": user.id}).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active franchise profile required")
    return int(row["id"])


def require_franchise_or_superuser(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    roles = get_user_role_names(db, user.id)
    if "SuperUser" in roles:
        return user
    if "FranchiseUser" in roles:
        get_current_franchise_user_id(db, user)
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Franchise or SuperUser access required")


def assert_franchise_scope(db: Session, user: User, franchise_user_id: int | None) -> None:
    roles = get_user_role_names(db, user.id)
    if "SuperUser" in roles:
        return
    if "FranchiseUser" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Franchise access required")
    own_franchise_id = get_current_franchise_user_id(db, user)
    if franchise_user_id is None or int(franchise_user_id) != own_franchise_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This record is outside your franchise scope")
