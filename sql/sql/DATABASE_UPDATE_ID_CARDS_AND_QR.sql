-- Run this once in DBeaver before using ID photos / ID card PDFs.
-- Safe to run multiple times.

ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL;

ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL;
ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL;
ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL;

ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL;

-- QR audit columns used by attendance PDF exports.
ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_area_id INTEGER NULL;
ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_office_name VARCHAR(255) NULL;
ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_token_hash VARCHAR(128) NULL;
