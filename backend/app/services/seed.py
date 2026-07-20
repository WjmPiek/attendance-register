from datetime import date

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.core import (
    Allocation,
    Area,
    EmployeeUser,
    FranchiseUser,
    GPSAllocationPerUser,
    GPSRule,
    Import,
    ImportRow,
    ManagerUser,
    MonthlyMetric,
    Permission,
    Role,
    RolePermission,
    SignatureBlock,
    SuperUser,
    TimeRegistrarRule,
    User,
    UserRole,
    UserEmployeeAccess,
    UserFranchiseAccess,
    UserManagerAccess,
    UserSuperUserAccess,
)


def seed_initial_data() -> None:
    db: Session = SessionLocal()
    try:
        if db.query(Role).count() == 0:
            roles = [
                Role(name="SuperUser", description="Full system access"),
                Role(name="FranchiseUser", description="Franchise scoped access"),
                Role(name="ManagerUser", description="Manager scoped access"),
                Role(name="EmployeeUser", description="Employee self-service access"),
            ]
            db.add_all(roles)
            db.flush()

            permissions = [
                Permission(code="users.read", description="Read users"),
                Permission(code="users.write", description="Write users"),
                Permission(code="roles.read", description="Read roles"),
                Permission(code="imports.write", description="Create imports"),
                Permission(code="metrics.read", description="Read metrics"),
                Permission(code="allocations.write", description="Manage allocations"),
            ]
            db.add_all(permissions)
            db.flush()

            role_map = {r.name: r for r in roles}
            perm_map = {p.code: p for p in permissions}

            assignments = {
                "SuperUser": list(perm_map.keys()),
                "FranchiseUser": ["users.read", "metrics.read", "allocations.write"],
                "ManagerUser": ["users.read", "metrics.read"],
                "EmployeeUser": ["metrics.read"],
            }
            for role_name, codes in assignments.items():
                for code in codes:
                    db.add(RolePermission(role_id=role_map[role_name].id, permission_id=perm_map[code].id))

        admin = db.query(User).filter(User.email == "admin@example.com").first()
        if not admin:
            admin = User(
                full_name="System Administrator",
                email="admin@example.com",
                password_hash=hash_password("Admin123!"),
                is_active=True,
            )
            db.add(admin)
            db.flush()

            super_role = db.query(Role).filter(Role.name == "SuperUser").first()
            db.add(UserRole(user_id=admin.id, role_id=super_role.id))
            db.add(SuperUser(user_id=admin.id, notes="Default seeded super user"))

        employee_user = db.query(User).filter(User.email == "employee@example.com").first()
        if not employee_user:
            employee_user = User(
                full_name="Demo Employee",
                email="employee@example.com",
                password_hash=hash_password("Employee123!"),
                is_active=True,
            )
            db.add(employee_user)
            db.flush()

            employee_role = db.query(Role).filter(Role.name == "EmployeeUser").first()
            db.add(UserRole(user_id=employee_user.id, role_id=employee_role.id))
            db.add(EmployeeUser(user_id=employee_user.id, employee_number="EMP-MOBILE-001"))
            db.add(SignatureBlock(user_id=employee_user.id, reason=None, is_blocked=False))

        if db.query(Area).count() == 0:
            area = Area(name="Head Office", code="HO", description="Primary operating area")
            db.add(area)
            db.flush()

            tr = TimeRegistrarRule(
                name="Default Time Rule",
                late_after_minutes=10,
                early_leave_before_minutes=10,
                allow_manual_override=True,
                is_active=True,
            )
            gps = GPSRule(
                name="Default GPS Rule",
                require_gps_on_clock_in=True,
                require_gps_on_clock_out=True,
                allowed_radius_meters=150,
                is_active=True,
            )
            db.add_all([tr, gps])
            db.flush()

            db.add(GPSAllocationPerUser(
                user_id=admin.id,
                area_id=area.id,
                latitude="-26.2041",
                longitude="28.0473",
                radius_meters=150,
                is_active=True,
            ))
            db.add(Allocation(
                user_id=admin.id,
                area_id=area.id,
                time_registrar_rule_id=tr.id,
                gps_rule_id=gps.id,
                is_active=True,
            ))
            db.add(SignatureBlock(user_id=admin.id, reason=None, is_blocked=False))
            db.add(GPSAllocationPerUser(
                user_id=employee_user.id,
                area_id=area.id,
                latitude="-26.2041",
                longitude="28.0473",
                radius_meters=150,
                is_active=True,
            ))
            db.add(Allocation(
                user_id=employee_user.id,
                area_id=area.id,
                time_registrar_rule_id=tr.id,
                gps_rule_id=gps.id,
                is_active=True,
            ))
            db.add(MonthlyMetric(user_id=admin.id, metric_month=date(2026, 4, 1), total_days_present=20, late_count=1, absent_count=0, attendance_score=95))
            imp = Import(file_name="seed_import.csv", imported_by_user_id=admin.id, status="completed", total_rows=1, successful_rows=1, failed_rows=0)
            db.add(imp)
            db.flush()
            db.add(ImportRow(import_id=imp.id, row_number=1, raw_payload='{"example": true}', status="completed"))

            franchise = FranchiseUser(user_id=admin.id, franchise_name="Default Franchise")
            manager = ManagerUser(user_id=admin.id, manager_code="MGR-001")
            employee = EmployeeUser(user_id=admin.id, employee_number="EMP-001")
            db.add_all([franchise, manager, employee])
            db.flush()

            db.add(UserSuperUserAccess(granter_user_id=admin.id, target_user_id=admin.id))
            db.add(UserFranchiseAccess(user_id=admin.id, franchise_user_id=franchise.id))
            db.add(UserManagerAccess(user_id=admin.id, manager_user_id=manager.id))
            db.add(UserEmployeeAccess(user_id=admin.id, employee_user_id=employee.id))

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
