-- Phase 1-5 upgrade: approvals, signatures, dashboard, notifications

ALTER TABLE franchise_registrations
ADD COLUMN IF NOT EXISTS approved_by_user_id INT,
ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS rejected_reason TEXT,
ADD COLUMN IF NOT EXISTS manager_note TEXT,
ADD COLUMN IF NOT EXISTS notification_status VARCHAR(30) DEFAULT 'pending';

ALTER TABLE attendance_events
ADD COLUMN IF NOT EXISTS approval_status VARCHAR(30) DEFAULT 'pending',
ADD COLUMN IF NOT EXISTS work_location_type VARCHAR(30),
ADD COLUMN IF NOT EXISTS employee_note TEXT,
ADD COLUMN IF NOT EXISTS manager_note TEXT,
ADD COLUMN IF NOT EXISTS approved_by_user_id INT,
ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS rejected_reason TEXT,
ADD COLUMN IF NOT EXISTS signature_required BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS signature_status VARCHAR(30);

CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    recipient_email VARCHAR(255),
    recipient_number VARCHAR(50),
    notification_type VARCHAR(80) NOT NULL,
    subject VARCHAR(255),
    message TEXT,
    status VARCHAR(30) DEFAULT 'pending',
    related_table VARCHAR(100),
    related_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attendance_approval_audit (
    id SERIAL PRIMARY KEY,
    attendance_event_id INT NOT NULL,
    action VARCHAR(30) NOT NULL,
    note TEXT,
    acted_by_user_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_attendance_events_approval_status
ON attendance_events(approval_status);

CREATE INDEX IF NOT EXISTS idx_attendance_events_work_location_type
ON attendance_events(work_location_type);

CREATE INDEX IF NOT EXISTS idx_franchise_registrations_status
ON franchise_registrations(status);
