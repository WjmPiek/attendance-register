"""Production schema guard.

The application no longer treats endpoint requests as a migration mechanism.
This guard verifies that the Alembic-managed operational schema is available at
startup and provides one actionable error when a deployment is behind.
"""
from sqlalchemy import inspect

REQUIRED_TABLES = {
    'users', 'roles', 'user_roles', 'franchise_users', 'manager_users',
    'employee_users', 'areas', 'attendance_events', 'commission_structures',
    'commission_entries', 'notifications', 'leave_applications',
    'payroll_imports', 'payroll_import_rows', 'payroll_payslips',
    'irp5_documents', 'password_reset_tokens',
}


def assert_operational_schema(engine) -> None:
    existing = set(inspect(engine).get_table_names())
    missing = sorted(REQUIRED_TABLES - existing)
    if missing:
        raise RuntimeError(
            'Database schema is behind the application. Run '
            '`python -m alembic upgrade head`. Missing tables: ' + ', '.join(missing)
        )
