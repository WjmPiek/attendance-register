from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models.core import User, UserRole


def role_names(db: Session, user: User) -> list[str]:
    return [ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]


def scoped_user_ids_sql(db: Session, user: User):
    """
    Returns a tuple: (where_sql, params)
    Use the SQL after WHERE/AND to restrict attendance records.
    """
    roles = role_names(db, user)

    if "SuperUser" in roles:
        return "1 = 1", {}

    if "FranchiseUser" in roles:
        franchise = db.execute(text("""
            SELECT id
            FROM franchise_users
            WHERE user_id = :user_id
            AND COALESCE(is_active, TRUE) = TRUE
        """), {"user_id": user.id}).mappings().first()

        if not franchise:
            raise HTTPException(status_code=403, detail="No active franchise profile found")

        return """
            attendance_events.user_id IN (
                SELECT user_id
                FROM employee_users
                WHERE franchise_user_id = :franchise_user_id
                UNION
                SELECT user_id
                FROM manager_users
                WHERE franchise_user_id = :franchise_user_id
                UNION
                SELECT user_id
                FROM franchise_users
                WHERE id = :franchise_user_id
            )
        """, {"franchise_user_id": franchise["id"]}

    if "ManagerUser" in roles:
        manager = db.execute(text("""
            SELECT id
            FROM manager_users
            WHERE user_id = :user_id
            AND COALESCE(is_active, TRUE) = TRUE
        """), {"user_id": user.id}).mappings().first()

        if not manager:
            raise HTTPException(status_code=403, detail="No active manager profile found")

        return """
            attendance_events.user_id IN (
                SELECT user_id
                FROM employee_users
                WHERE manager_user_id = :manager_user_id
                UNION
                SELECT :current_user_id
            )
        """, {"manager_user_id": manager["id"], "current_user_id": user.id}

    return "attendance_events.user_id = :current_user_id", {"current_user_id": user.id}
