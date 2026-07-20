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
        db.execute(text("SET lock_timeout = '10s'"))
        db.execute(text("SET statement_timeout = '60s'"))
        
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
        _add_column(db, 'manager_users', 'id_number', 'VARCHAR(30)')
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
        _add_column(db, 'employee_users', 'id_number', 'VARCHAR(30)')
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

        db.execute(text("""
        CREATE TABLE IF NOT EXISTS commission_structures (
            id SERIAL PRIMARY KEY, franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id) ON DELETE CASCADE,
            commission_type VARCHAR(80) NOT NULL, label VARCHAR(120) NOT NULL, calculation_type VARCHAR(30) NOT NULL,
            rate NUMERIC(12,2) NOT NULL DEFAULT 0, overtime_multiplier NUMERIC(8,2) NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by_user_id INTEGER NOT NULL REFERENCES users(id), created_at TIMESTAMP NOT NULL DEFAULT NOW(), updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(franchise_user_id, commission_type)
        )
        """))
        db.execute(text("""
        CREATE TABLE IF NOT EXISTS commission_entries (
            id SERIAL PRIMARY KEY, franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id) ON DELETE CASCADE,
            employee_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, commission_type VARCHAR(80) NOT NULL,
            service_date DATE NOT NULL, reference VARCHAR(255) NULL, quantity NUMERIC(12,2) NOT NULL DEFAULT 1,
            invoice_value_before_tax NUMERIC(14,2) NULL, hours NUMERIC(10,2) NULL, hourly_rate NUMERIC(12,2) NULL,
            applied_rate NUMERIC(12,2) NOT NULL, calculated_amount NUMERIC(14,2) NOT NULL, notes TEXT NULL,
            created_by_user_id INTEGER NOT NULL REFERENCES users(id), created_at TIMESTAMP NOT NULL DEFAULT NOW(), updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_commission_entries_employee_date ON commission_entries(employee_user_id, service_date)"))

        db.execute(text("""
        CREATE TABLE IF NOT EXISTS payroll_payslips (
            id SERIAL PRIMARY KEY,
            import_id INTEGER NULL REFERENCES payroll_imports(id) ON DELETE SET NULL,
            user_id INTEGER NOT NULL,
            franchise_user_id INTEGER NULL,
            employee_key VARCHAR(255) NULL,
            original_filename VARCHAR(255) NOT NULL,
            zip_filename VARCHAR(255) NULL,
            file_content BYTEA NOT NULL,
            content_type VARCHAR(120) NOT NULL DEFAULT 'application/zip',
            uploaded_by_user_id INTEGER NOT NULL,
            uploaded_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """))

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
