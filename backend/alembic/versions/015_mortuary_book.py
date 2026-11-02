"""Scoped Mortuary Book policies and auditable removal import identities."""
from alembic import op

revision = '015_mortuary_book'
down_revision = '014_staff_integrity_constraints'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE mortuary_policies (
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        employee_user_id INTEGER NOT NULL DEFAULT 0,
        policy TEXT NOT NULL,
        updated_by_user_id INTEGER NOT NULL REFERENCES users(id),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY(franchise_user_id, employee_user_id)
    )''')
    op.execute('ALTER TABLE commission_entries ADD COLUMN branch_name VARCHAR(255) NULL')
    op.execute('''CREATE TABLE mortuary_import_allocations (
        id SERIAL PRIMARY KEY,
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        employee_user_id INTEGER NOT NULL REFERENCES users(id),
        branch_key VARCHAR(255) NOT NULL,
        reference_key VARCHAR(255) NOT NULL,
        entry_id INTEGER NOT NULL REFERENCES commission_entries(id),
        source_hash VARCHAR(64) NOT NULL,
        source_filename VARCHAR(255) NOT NULL,
        source_page INTEGER NOT NULL,
        removal_role VARCHAR(20) NOT NULL,
        date_in DATE NOT NULL,
        time_in VARCHAR(5) NOT NULL,
        fee_band VARCHAR(10) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE(franchise_user_id, employee_user_id, branch_key, reference_key)
    )''')


def downgrade():
    # Preserve financial source history.
    pass
