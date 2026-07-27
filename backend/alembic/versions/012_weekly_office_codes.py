"""Rotate office attendance codes once per ISO week.

Revision ID: 012_weekly_office_codes
Revises: 011_attendance_office_code
"""
from alembic import op


revision = "012_weekly_office_codes"
down_revision = "011_attendance_office_code"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_valid_week VARCHAR(10) NULL")
    # Force each active office to receive a fresh code on its first list,
    # print, validation, sign-in or sign-out request after deployment.
    op.execute(
        """
        UPDATE areas
        SET qr_valid_week = NULL
        WHERE franchise_user_id IS NOT NULL
          AND COALESCE(is_archived, FALSE) = FALSE
        """
    )


def downgrade():
    # Weekly code state is intentionally retained.
    pass
