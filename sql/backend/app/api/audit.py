from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_user_role_names, get_current_franchise_user_id
from app.db.session import get_db
from app.models.core import User
from app.services.audit import ensure_audit_log_table

router = APIRouter()


@router.get("/logs")
def list_audit_logs(
    entity_type: str = Query(default=""),
    action: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_audit_log_table(db)
    roles = get_user_role_names(db, current_user.id)
    params = {"limit": limit}
    where = []
    if entity_type:
        where.append("entity_type = :entity_type")
        params["entity_type"] = entity_type
    if action:
        where.append("action = :action")
        params["action"] = action
    if "SuperUser" not in roles:
        franchise_user_id = get_current_franchise_user_id(db, current_user)
        where.append("franchise_user_id = :franchise_user_id")
        params["franchise_user_id"] = franchise_user_id
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    rows = db.execute(text(f"""
        SELECT al.*, u.full_name AS actor_name, u.email AS actor_email
        FROM audit_logs al
        LEFT JOIN users u ON u.id = al.actor_user_id
        {where_sql}
        ORDER BY al.created_at DESC, al.id DESC
        LIMIT :limit
    """), params).mappings().all()
    return [dict(row) for row in rows]
