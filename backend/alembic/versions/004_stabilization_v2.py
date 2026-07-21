"""Version 2 production schema stabilization.

Consolidates fields that were previously created lazily by API endpoints.
All statements are idempotent and preserve existing data.
"""
from alembic import op

revision = "004_stabilization_v2"
down_revision = "003_payslip_documents"
branch_labels = None
depends_on = None


def upgrade():
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username ON users(username) WHERE username IS NOT NULL",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo BYTEA",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255)",
        "ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS business_name VARCHAR(255)",
        "ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS trading_as VARCHAR(255)",
        "ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS business_registration_number VARCHAR(100)",
        "ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS vat_number VARCHAR(100)",
        "ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS office_address TEXT",
        "ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(500)",
        "ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS office_number VARCHAR(50)",
        "ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS twenty_four_hour_number VARCHAR(50)",
        "ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50)",
        "ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS franchise_user_id INTEGER REFERENCES franchise_users(id)",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS name VARCHAR(120)",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS surname VARCHAR(120)",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50)",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS office_address_assigned TEXT",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS area_id INTEGER REFERENCES areas(id)",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS work_start_time VARCHAR(5) DEFAULT '08:00'",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS work_end_time VARCHAR(5) DEFAULT '17:00'",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo BYTEA",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80)",
        "ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255)",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS franchise_user_id INTEGER REFERENCES franchise_users(id)",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS manager_user_id INTEGER REFERENCES manager_users(id)",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS employee_role VARCHAR(80) DEFAULT 'Employee'",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS name VARCHAR(120)",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS surname VARCHAR(120)",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50)",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS office_address_assigned TEXT",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS area_id INTEGER REFERENCES areas(id)",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS work_start_time VARCHAR(5) DEFAULT '08:00'",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS work_end_time VARCHAR(5) DEFAULT '17:00'",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo BYTEA",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80)",
        "ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255)",
        "ALTER TABLE areas ADD COLUMN IF NOT EXISTS franchise_user_id INTEGER REFERENCES franchise_users(id)",
        "ALTER TABLE areas ADD COLUMN IF NOT EXISTS office_address TEXT",
        "ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_token VARCHAR(120)",
        "ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_enabled BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_updated_at TIMESTAMP",
        "ALTER TABLE areas ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE areas ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP",
        "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS signature_image BYTEA",
        "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS signature_image_mime VARCHAR(80)",
        "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS signature_image_filename VARCHAR(255)",
        "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_area_id INTEGER REFERENCES areas(id)",
        "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_office_name VARCHAR(255)",
        "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_token_hash VARCHAR(128)",
        "CREATE INDEX IF NOT EXISTS ix_manager_users_franchise_active ON manager_users(franchise_user_id, is_active)",
        "CREATE INDEX IF NOT EXISTS ix_employee_users_franchise_active ON employee_users(franchise_user_id, is_active)",
        "CREATE INDEX IF NOT EXISTS ix_employee_users_manager ON employee_users(manager_user_id)",
        "CREATE INDEX IF NOT EXISTS ix_areas_franchise_archived ON areas(franchise_user_id, is_archived)",
    ]
    for statement in statements:
        op.execute(statement)

    op.execute("""
    CREATE TABLE IF NOT EXISTS commission_structures (
        id SERIAL PRIMARY KEY, franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id) ON DELETE CASCADE,
        commission_type VARCHAR(80) NOT NULL, label VARCHAR(120) NOT NULL, calculation_type VARCHAR(30) NOT NULL,
        rate NUMERIC(12,2) NOT NULL DEFAULT 0, overtime_multiplier NUMERIC(8,2), is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_by_user_id INTEGER NOT NULL REFERENCES users(id), created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(), UNIQUE(franchise_user_id, commission_type)
    )""")
    op.execute("""
    CREATE TABLE IF NOT EXISTS commission_entries (
        id SERIAL PRIMARY KEY, franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id) ON DELETE CASCADE,
        employee_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, commission_type VARCHAR(80) NOT NULL,
        service_date DATE NOT NULL, reference VARCHAR(255), quantity NUMERIC(12,2) NOT NULL DEFAULT 1,
        invoice_value_before_tax NUMERIC(14,2), hours NUMERIC(10,2), hourly_rate NUMERIC(12,2),
        applied_rate NUMERIC(12,2) NOT NULL, calculated_amount NUMERIC(14,2) NOT NULL, notes TEXT,
        status VARCHAR(30) NOT NULL DEFAULT 'approved', submitted_at TIMESTAMP, reviewed_at TIMESTAMP,
        reviewed_by_user_id INTEGER REFERENCES users(id), review_notes TEXT,
        last_edited_by_user_id INTEGER REFERENCES users(id), created_by_user_id INTEGER NOT NULL REFERENCES users(id),
        created_at TIMESTAMP NOT NULL DEFAULT NOW(), updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_entries_employee_date ON commission_entries(employee_user_id, service_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_entries_status ON commission_entries(franchise_user_id, status, created_at DESC)")


def downgrade():
    # Intentionally non-destructive: production history and documents must be retained.
    pass
