"""Require reusable four-digit office attendance codes.

Revision ID: 011_attendance_office_code
Revises: 010_attendance_mobile_integrity
"""
from alembic import op


revision = "011_attendance_office_code"
down_revision = "010_attendance_mobile_integrity"
branch_labels = None
depends_on = None


def upgrade():
    # Existing long QR tokens are replaced with a unique four-digit office
    # code. The code remains in qr_token so existing deployments and printed
    # QR support continue to work without a second source of truth.
    op.execute(
        """
        DO $$
        DECLARE
            office_row RECORD;
            candidate INTEGER;
        BEGIN
            FOR office_row IN
                SELECT id
                FROM areas
                WHERE franchise_user_id IS NOT NULL
                ORDER BY id
            LOOP
                candidate := 1000 + MOD(office_row.id * 7919, 9000);
                WHILE EXISTS (
                    SELECT 1
                    FROM areas
                    WHERE id <> office_row.id
                      AND qr_token = LPAD(candidate::text, 4, '0')
                ) LOOP
                    candidate := 1000 + MOD(candidate - 999, 9000);
                END LOOP;

                UPDATE areas
                SET qr_token = LPAD(candidate::text, 4, '0'),
                    qr_enabled = TRUE,
                    qr_updated_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = office_row.id;
            END LOOP;
        END $$;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_areas_active_office_code
        ON areas(qr_token)
        WHERE qr_token IS NOT NULL
          AND franchise_user_id IS NOT NULL
          AND COALESCE(is_archived, FALSE) = FALSE
        """
    )


def downgrade():
    # Attendance office codes are intentionally retained.
    pass
