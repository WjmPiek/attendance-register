from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.core import Role
from app.schemas.role import RoleListItem

router = APIRouter()


@router.get("", response_model=list[RoleListItem])
def list_roles(db: Session = Depends(get_db), _=Depends(require_roles("SuperUser", "FranchiseUser", "ManagerUser"))):
    roles = db.query(Role).order_by(Role.id).all()
    return [
        RoleListItem(
            id=role.id,
            name=role.name,
            description=role.description,
            permissions=[rp.permission.code for rp in role.permissions],
        )
        for role in roles
    ]
