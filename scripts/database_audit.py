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
    "attendance_events": {"id", "user_id", "action", "qr_area_id", "qr_office_name", "qr_token_hash"},
    "commission_structures": {"id", "franchise_user_id", "commission_type", "rate", "is_active"},
    "commission_entries": {"id", "franchise_user_id", "employee_user_id", "service_date", "calculated_amount", "status"},
    "leave_applications": {"id", "applicant_user_id", "franchise_user_id", "status"},
    "irp5_documents": {"id", "target_user_id", "franchise_user_id", "original_filename", "is_active"},
    "payroll_payslips": {"id", "user_id", "franchise_user_id", "original_filename", "file_content", "is_active"},
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

    integrity_queries = {
        "employees_without_user": "SELECT COUNT(*) FROM employee_users e LEFT JOIN users u ON u.id=e.user_id WHERE u.id IS NULL",
        "employees_without_franchise": "SELECT COUNT(*) FROM employee_users WHERE franchise_user_id IS NULL",
        "managers_without_user": "SELECT COUNT(*) FROM manager_users m LEFT JOIN users u ON u.id=m.user_id WHERE u.id IS NULL",
        "managers_without_franchise": "SELECT COUNT(*) FROM manager_users WHERE franchise_user_id IS NULL",
        "active_staff_on_archived_address": """
            SELECT COUNT(*) FROM (
                SELECT user_id, area_id FROM employee_users WHERE COALESCE(is_active, TRUE)=TRUE
                UNION ALL
                SELECT user_id, area_id FROM manager_users WHERE COALESCE(is_active, TRUE)=TRUE
            ) s JOIN areas a ON a.id=s.area_id WHERE COALESCE(a.is_archived, FALSE)=TRUE
        """,
        "commission_entries_without_user": "SELECT COUNT(*) FROM commission_entries c LEFT JOIN users u ON u.id=c.employee_user_id WHERE u.id IS NULL",
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

    print("\nPASS: schema and core relationships are valid.")


if __name__ == "__main__":
    main()
