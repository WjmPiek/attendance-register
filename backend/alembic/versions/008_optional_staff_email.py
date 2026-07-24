"""Allow username-only staff accounts.

Some legacy databases created users.email as NOT NULL even though the current
model and login flow allow a username in place of an email address.
"""
from alembic import op


revision = "008_optional_staff_email"
down_revision = "007_staff_hierarchy_integrity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ALTER COLUMN email DROP NOT NULL")


def downgrade():
    # Existing username-only accounts make restoring NOT NULL unsafe.
    pass
