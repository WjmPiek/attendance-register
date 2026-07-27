"""Read-only production database audit for Render PostgreSQL."""
from __future__ import annotations

from sqlalchemy import inspect, text

from app.db.session import engine

REQUIRED_COLUMNS = {
    "users": {"id", "full_name", "email", "username", "password_hash", "is_active"},
    "franchise_users": {"id", "user_id", "business_name", "office_address", "is_active"},
    "manager_users": {"id", "user_id", "franchise_user_id", "employee_number", "name", "surname", "email", "office_address_assigned", "is_active"},
    "employee_users": {"id", "user_id", "franchise_user_id", "manager_user_id", "employee_role", "employee_number", "name", "surname", "email", "office_address_assigned", "is_active"},
    "areas": {"id", "franchise_user_id", "office_address", "qr_token", "qr_enabled", "is_archived", "archived_at"},
    "attendance_events": {"id", "user_id", "action", "qr_area_id", "qr_office_name", "qr_token_hash", "attendance_photo", "attendance_photo_mime", "attendance_photo_filename", "photo_status"},
    "commission_structures": {"id", "franchise_user_id", "commission_type", "rate", "is_active"},
    "commission_entries": {"id", "franchise_user_id", "employee_user_id", "service_date", "calculated_amount", "status"},
    "leave_applications": {"id", "applicant_user_id", "franchise_user_id", "status"},
    "irp5_documents": {"id", "target_user_id", "franchise_user_id", "original_filename", "is_active"},
    "payroll_payslips": {"id", "user_id", "franchise_user_id", "original_filename", "file_content", "is_active"},
}

REQUIRED_NULLABLE_COLUMNS = {
    "users": {"email", "username"},
}


def main() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    failures: list[str] = []

    print("DATABASE SCHEMA AUDIT")
    print("=" * 72)
    for table, required in REQUIRED_COLUMNS.items():
        if table not in tables:
            failures.append(f"Missing table: {table}")
            continue
        actual = {column["name"] for column in inspector.get_columns(table)}
        for column in sorted(required - actual):
            failures.append(f"Missing column: {table}.{column}")
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        for column in sorted(REQUIRED_NULLABLE_COLUMNS.get(table, set())):
            if column in columns and not columns[column].get("nullable", False):
                failures.append(f"Column must allow NULL: {table}.{column}")

    integrity_queries = {
        "missing_required_system_roles": """
            SELECT 4 - COUNT(*)
            FROM roles
            WHERE name IN ('SuperUser', 'FranchiseUser', 'ManagerUser', 'EmployeeUser')
        """,
        "employees_without_user": "SELECT COUNT(*) FROM employee_users e LEFT JOIN users u ON u.id=e.user_id WHERE u.id IS NULL",
        "employees_without_franchise": "SELECT COUNT(*) FROM employee_users WHERE franchise_user_id IS NULL",
        "managers_without_user": "SELECT COUNT(*) FROM manager_users m LEFT JOIN users u ON u.id=m.user_id WHERE u.id IS NULL",
        "managers_without_franchise": "SELECT COUNT(*) FROM manager_users WHERE franchise_user_id IS NULL",
        "employees_with_wrong_role": """
            SELECT COUNT(*)
            FROM employee_users eu
            WHERE NOT EXISTS (
                SELECT 1 FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = eu.user_id AND r.name = 'EmployeeUser'
            )
        """,
        "managers_with_wrong_role": """
            SELECT COUNT(*)
            FROM manager_users mu
            WHERE NOT EXISTS (
                SELECT 1 FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = mu.user_id AND r.name = 'ManagerUser'
            )
        """,
        "cross_franchise_manager_assignments": """
            SELECT COUNT(*)
            FROM employee_users eu
            JOIN manager_users mu ON mu.id = eu.manager_user_id
            WHERE eu.franchise_user_id <> mu.franchise_user_id
        """,
        "active_staff_without_one_valid_office": """
            SELECT COUNT(*)
            FROM (
                SELECT s.user_id
                FROM (
                    SELECT user_id, franchise_user_id
                    FROM employee_users
                    WHERE COALESCE(is_active, TRUE) = TRUE
                    UNION ALL
                    SELECT user_id, franchise_user_id
                    FROM manager_users
                    WHERE COALESCE(is_active, TRUE) = TRUE
                ) s
                LEFT JOIN gps_allocations_per_user g
                    ON g.user_id = s.user_id AND COALESCE(g.is_active, TRUE) = TRUE
                LEFT JOIN areas a
                    ON a.id = g.area_id
                   AND a.franchise_user_id = s.franchise_user_id
                   AND COALESCE(a.is_archived, FALSE) = FALSE
                GROUP BY s.user_id
                HAVING COUNT(a.id) <> 1
            ) invalid_office
        """,
        "users_with_multiple_staff_profiles": """
            SELECT COUNT(*)
            FROM manager_users mu
            JOIN employee_users eu ON eu.user_id = mu.user_id
        """,
        "staff_with_wrong_role_count": """
            SELECT COUNT(*)
            FROM (
                SELECT u.id
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.id
                WHERE EXISTS (SELECT 1 FROM manager_users mu WHERE mu.user_id = u.id)
                   OR EXISTS (SELECT 1 FROM employee_users eu WHERE eu.user_id = u.id)
                GROUP BY u.id
                HAVING COUNT(*) <> 1
            ) invalid_roles
        """,
        "commission_entries_without_employee": """
            SELECT COUNT(*)
            FROM commission_entries c
            LEFT JOIN employee_users eu ON eu.id = c.employee_user_id
            WHERE c.employee_user_id IS NOT NULL AND eu.id IS NULL
        """,
    }

    if not failures:
        with engine.connect() as connection:
            print("\nDATA INTEGRITY")
            for name, query in integrity_queries.items():
                value = int(connection.execute(text(query)).scalar() or 0)
                print(f"{name}: {value}")
                if value:
                    failures.append(f"Integrity issue {name}: {value}")

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print(" -", failure)
        raise SystemExit(1)

    print("\nPASS: schema and Phase 1 staff relationships are valid.")


if __name__ == "__main__":
    main()
