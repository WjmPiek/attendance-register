"""Complete the Phase 3 mobile attendance evidence schema."""
from alembic import op


revision = "010_attendance_mobile_integrity"
down_revision = "009_commission_workflow"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS attendance_photo BYTEA NULL")
    op.execute("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS attendance_photo_mime VARCHAR(80) NULL")
    op.execute("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS attendance_photo_filename VARCHAR(255) NULL")
    op.execute("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS photo_status VARCHAR(30) NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_events_user_created ON attendance_events(user_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_events_approval_created ON attendance_events(approval_status, created_at DESC)")


def downgrade():
    # Attendance evidence is intentionally retained.
    pass
