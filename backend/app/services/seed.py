"""Create only immutable authorization reference data.

Production startup must never recreate demo users, demo staff, demo franchises, or
sample attendance data after a database cleanup.
"""
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.core import Permission, Role, RolePermission


def seed_initial_data() -> None:
    db: Session = SessionLocal()
    try:
        role_definitions = {
            "SuperUser": "Full system access",
            "FranchiseUser": "Franchise scoped access",
            "ManagerUser": "Manager scoped access",
            "EmployeeUser": "Employee self-service access",
        }
        for name, description in role_definitions.items():
            if not db.query(Role).filter(Role.name == name).first():
                db.add(Role(name=name, description=description))
        db.flush()

        permission_definitions = {
            "users.read": "Read users",
            "users.write": "Write users",
            "roles.read": "Read roles",
            "imports.write": "Create imports",
            "metrics.read": "Read metrics",
            "allocations.write": "Manage allocations",
        }
        for code, description in permission_definitions.items():
            if not db.query(Permission).filter(Permission.code == code).first():
                db.add(Permission(code=code, description=description))
        db.flush()

        roles = {row.name: row for row in db.query(Role).all()}
        permissions = {row.code: row for row in db.query(Permission).all()}
        assignments = {
            "SuperUser": list(permission_definitions),
            "FranchiseUser": ["users.read", "metrics.read", "allocations.write"],
            "ManagerUser": ["users.read", "metrics.read"],
            "EmployeeUser": ["metrics.read"],
        }
        for role_name, codes in assignments.items():
            for code in codes:
                exists = db.query(RolePermission).filter(
                    RolePermission.role_id == roles[role_name].id,
                    RolePermission.permission_id == permissions[code].id,
                ).first()
                if not exists:
                    db.add(RolePermission(
                        role_id=roles[role_name].id,
                        permission_id=permissions[code].id,
                    ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
