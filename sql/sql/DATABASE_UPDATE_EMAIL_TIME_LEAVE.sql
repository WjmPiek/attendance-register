-- Run in DBeaver on attendance_db before testing v18.
-- This keeps the notification outbox, leave decisions and email tracking compatible.

ALTER TABLE notifications ADD COLUMN IF NOT EXISTS recipient_user_id INTEGER NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS franchise_user_id INTEGER NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS recipient_email VARCHAR(255) NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS recipient_number VARCHAR(80) NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS severity VARCHAR(40) NOT NULL DEFAULT 'info';
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS target_tab VARCHAR(80) NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS sent_at TIMESTAMP NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS error_message TEXT NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;

CREATE INDEX IF NOT EXISTS idx_notifications_franchise_created
ON notifications (franchise_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notifications_recipient_created
ON notifications (recipient_user_id, created_at DESC);

ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS decision_note TEXT NULL;
ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS decided_by_user_id INTEGER NULL;
ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS decided_at TIMESTAMP NULL;
ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;
