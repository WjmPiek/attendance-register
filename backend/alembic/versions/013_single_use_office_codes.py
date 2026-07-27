"""Make office attendance codes single-use with a 20-minute expiry.

Revision ID: 013_single_use_office_codes
Revises: 012_weekly_office_codes
"""
from alembic import op


revision = "013_single_use_office_codes"
down_revision = "012_weekly_office_codes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_expires_at TIMESTAMP NULL")
    op.execute("ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_last_used_at TIMESTAMP NULL")
    # Force a fresh short-lived code the next time a manager or franchise user
    # opens the office-code screen.
    op.execute(
        """
        UPDATE areas
        SET qr_expires_at = NULL
        WHERE franchise_user_id IS NOT NULL
          AND COALESCE(is_archived, FALSE) = FALSE
        """
    )


def downgrade():
    # Code audit timestamps are intentionally retained.
    pass
