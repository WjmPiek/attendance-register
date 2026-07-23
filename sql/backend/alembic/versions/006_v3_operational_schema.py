"""Version 3 operational schema baseline.

Moves the remaining lazily-created operational tables into Alembic and adds
indexes/foreign keys needed by the staff, leave, payroll, IRP5 and notification
workflows. Statements are idempotent so upgraded production databases are safe.
"""
from alembic import op

revision = "006_v3_operational_schema"
down_revision = "005_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade():
    statements = [
        """CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NULL REFERENCES users(id) ON DELETE CASCADE,
            recipient_user_id INTEGER NULL REFERENCES users(id) ON DELETE CASCADE,
            franchise_user_id INTEGER NULL REFERENCES franchise_users(id) ON DELETE CASCADE,
            recipient_email VARCHAR(255) NULL,
            recipient_number VARCHAR(80) NULL,
            notification_type VARCHAR(80) NOT NULL DEFAULT 'system',
            subject VARCHAR(255) NOT NULL DEFAULT 'Notification',
            message TEXT NOT NULL DEFAULT '',
            status VARCHAR(40) NOT NULL DEFAULT 'pending',
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            severity VARCHAR(40) NOT NULL DEFAULT 'info',
            target_tab VARCHAR(80) NULL,
            related_table VARCHAR(120) NULL,
            related_id INTEGER NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NULL
        )""",
        """CREATE TABLE IF NOT EXISTS leave_applications (
            id SERIAL PRIMARY KEY,
            applicant_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            employee_user_id INTEGER NULL REFERENCES employee_users(id) ON DELETE SET NULL,
            franchise_user_id INTEGER NULL REFERENCES franchise_users(id) ON DELETE CASCADE,
            manager_user_id INTEGER NULL REFERENCES manager_users(id) ON DELETE SET NULL,
            leave_type VARCHAR(80) NOT NULL DEFAULT 'Annual Leave',
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            days_requested NUMERIC(8,2) NOT NULL DEFAULT 0,
            reason TEXT NULL,
            status VARCHAR(40) NOT NULL DEFAULT 'pending',
            decision_note TEXT NULL,
            decided_by_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
            decided_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NULL
        )""",
        """CREATE TABLE IF NOT EXISTS payroll_imports (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            payroll_month DATE NULL,
            franchise_user_id INTEGER NULL REFERENCES franchise_users(id) ON DELETE CASCADE,
            imported_by_user_id INTEGER NOT NULL REFERENCES users(id),
            imported_at TIMESTAMP NOT NULL DEFAULT NOW(),
            rows_total INTEGER NOT NULL DEFAULT 0,
            rows_matched INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(40) NOT NULL DEFAULT 'processed',
            updated_at TIMESTAMP NULL,
            deleted_at TIMESTAMP NULL,
            deleted_by_user_id INTEGER NULL REFERENCES users(id)
        )""",
        """CREATE TABLE IF NOT EXISTS payroll_import_rows (
            id SERIAL PRIMARY KEY,
            import_id INTEGER NOT NULL REFERENCES payroll_imports(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            matched_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
            employee_key VARCHAR(255) NULL,
            employee_name VARCHAR(255) NULL,
            email VARCHAR(255) NULL,
            match_method VARCHAR(80) NULL,
            status VARCHAR(40) NOT NULL DEFAULT 'unmatched',
            message TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS payroll_payslips (
            id SERIAL PRIMARY KEY,
            import_id INTEGER NULL REFERENCES payroll_imports(id) ON DELETE SET NULL,
            user_id INTEGER NULL REFERENCES users(id) ON DELETE CASCADE,
            franchise_user_id INTEGER NULL REFERENCES franchise_users(id) ON DELETE CASCADE,
            employee_key VARCHAR(255) NULL,
            original_filename VARCHAR(255) NULL,
            zip_filename VARCHAR(255) NULL,
            file_content BYTEA NULL,
            content_type VARCHAR(120) NOT NULL DEFAULT 'application/zip',
            uploaded_by_user_id INTEGER NULL REFERENCES users(id),
            uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            deleted_at TIMESTAMP NULL,
            deleted_by_user_id INTEGER NULL REFERENCES users(id)
        )""",
        """CREATE TABLE IF NOT EXISTS irp5_documents (
            id SERIAL PRIMARY KEY,
            employee_user_id INTEGER NULL REFERENCES employee_users(id) ON DELETE SET NULL,
            target_user_id INTEGER NULL REFERENCES users(id) ON DELETE CASCADE,
            uploaded_by_user_id INTEGER NULL REFERENCES users(id),
            franchise_user_id INTEGER NULL REFERENCES franchise_users(id) ON DELETE CASCADE,
            manager_user_id INTEGER NULL REFERENCES manager_users(id) ON DELETE SET NULL,
            original_filename VARCHAR(255) NULL,
            stored_filename VARCHAR(255) NULL,
            content_type VARCHAR(120) NULL,
            file_size INTEGER NULL,
            tax_year VARCHAR(20) NULL,
            notes TEXT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            document_type VARCHAR(40) NULL DEFAULT 'IRP5',
            target_staff_type VARCHAR(40) NULL DEFAULT 'employee',
            target_staff_id INTEGER NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NULL
        )""",
        "CREATE INDEX IF NOT EXISTS ix_notifications_recipient_unread ON notifications(recipient_user_id, is_read, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_notifications_franchise ON notifications(franchise_user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_leave_franchise_status ON leave_applications(franchise_user_id, status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_leave_applicant ON leave_applications(applicant_user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_payroll_imports_franchise ON payroll_imports(franchise_user_id, imported_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_payroll_payslips_user ON payroll_payslips(user_id, uploaded_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_irp5_target_user ON irp5_documents(target_user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_irp5_franchise ON irp5_documents(franchise_user_id, created_at DESC)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_manager_employee_number_per_franchise ON manager_users(franchise_user_id, employee_number) WHERE employee_number IS NOT NULL AND COALESCE(is_active, TRUE)=TRUE",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_employee_number_per_franchise ON employee_users(franchise_user_id, employee_number) WHERE employee_number IS NOT NULL AND COALESCE(is_active, TRUE)=TRUE",
    ]
    for statement in statements:
        op.execute(statement)


def downgrade():
    # Production data is intentionally retained.
    pass
