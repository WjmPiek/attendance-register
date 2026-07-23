"""Version 3.1 commission and attendance enhancements."""
from alembic import op

revision = "007_v31_commission_attendance"
down_revision = "006_v3_operational_schema"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS attendance_photo BYTEA NULL")
    op.execute("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS attendance_photo_mime VARCHAR(80) NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_entries_status_franchise ON commission_entries(franchise_user_id,status)")
    op.execute("""INSERT INTO commission_structures(franchise_user_id,commission_type,label,calculation_type,rate,overtime_multiplier,is_active,created_by_user_id,created_at,updated_at)
      SELECT f.id,'joinings','Joinings','fixed',0,NULL,TRUE,f.user_id,NOW(),NOW() FROM franchise_users f
      ON CONFLICT(franchise_user_id,commission_type) DO NOTHING""")

def downgrade():
    pass
