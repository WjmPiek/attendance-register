from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


def _columns(db: Session, table: str) -> set[str]:
    try:
        return {c['name'] for c in inspect(db.bind).get_columns(table)}
    except Exception:
        return set()


def _add_column(db: Session, table: str, name: str, ddl: str) -> None:
    if name not in _columns(db, table):
        db.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))


def ensure_runtime_schema() -> None:
    from app.db.session import SessionLocal
    db: Session = SessionLocal()
    try:
        # Login compatibility: staff can sign in with either email or username.
        _add_column(db, 'users', 'username', 'VARCHAR(100) UNIQUE')

        # Franchise/HR ownership and profile fields used by the staff API.
        _add_column(db, 'franchise_users', 'business_name', 'VARCHAR(255)')
        _add_column(db, 'franchise_users', 'trading_as', 'VARCHAR(255)')
        _add_column(db, 'franchise_users', 'business_registration_number', 'VARCHAR(100)')
        _add_column(db, 'franchise_users', 'vat_number', 'VARCHAR(100)')
        _add_column(db, 'franchise_users', 'office_address', 'TEXT')
        _add_column(db, 'franchise_users', 'website', 'VARCHAR(500)')
        _add_column(db, 'franchise_users', 'office_number', 'VARCHAR(50)')
        _add_column(db, 'franchise_users', 'twenty_four_hour_number', 'VARCHAR(50)')
        _add_column(db, 'franchise_users', 'contact_number', 'VARCHAR(50)')
        _add_column(db, 'franchise_users', 'is_active', 'BOOLEAN DEFAULT TRUE')

        _add_column(db, 'manager_users', 'franchise_user_id', 'INTEGER REFERENCES franchise_users(id)')
        _add_column(db, 'manager_users', 'name', 'VARCHAR(120)')
        _add_column(db, 'manager_users', 'surname', 'VARCHAR(120)')
        _add_column(db, 'manager_users', 'email', 'VARCHAR(255)')
        _add_column(db, 'manager_users', 'contact_number', 'VARCHAR(50)')
        _add_column(db, 'manager_users', 'office_address_assigned', 'TEXT')
        _add_column(db, 'manager_users', 'area_id', 'INTEGER REFERENCES areas(id)')
        _add_column(db, 'manager_users', 'is_active', 'BOOLEAN DEFAULT TRUE')

        _add_column(db, 'employee_users', 'franchise_user_id', 'INTEGER REFERENCES franchise_users(id)')
        _add_column(db, 'employee_users', 'manager_user_id', 'INTEGER REFERENCES manager_users(id)')
        _add_column(db, 'employee_users', 'employee_role', 'VARCHAR(80)')
        _add_column(db, 'employee_users', 'name', 'VARCHAR(120)')
        _add_column(db, 'employee_users', 'surname', 'VARCHAR(120)')
        _add_column(db, 'employee_users', 'email', 'VARCHAR(255)')
        _add_column(db, 'employee_users', 'contact_number', 'VARCHAR(50)')
        _add_column(db, 'employee_users', 'office_address_assigned', 'TEXT')
        _add_column(db, 'employee_users', 'area_id', 'INTEGER REFERENCES areas(id)')
        _add_column(db, 'employee_users', 'is_active', 'BOOLEAN DEFAULT TRUE')

        # Attendance signature image storage for PDF export.
        _add_column(db, 'attendance_events', 'signature_image', 'BYTEA')
        _add_column(db, 'attendance_events', 'signature_image_mime', 'VARCHAR(80)')
        _add_column(db, 'attendance_events', 'signature_image_filename', 'VARCHAR(255)')

        # Some DBs created from older code do not have these review note columns.
        _add_column(db, 'franchise_registrations', 'manager_note', 'TEXT')
        _add_column(db, 'franchise_registrations', 'website', 'VARCHAR(500)')

        # IRP5 manager ownership link.
        _add_column(db, 'irp5_documents', 'manager_user_id', 'INTEGER')

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
