-- Full patch: IRP5 manager link, username login, and franchise QR website fallback
ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100) UNIQUE;
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(500);
ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS manager_user_id INTEGER NULL;

-- Backfill usernames for existing users that do not have one.
UPDATE users
SET username = LOWER(REGEXP_REPLACE(COALESCE(NULLIF(split_part(email, '@', 1), ''), 'user_' || id::text), '[^a-zA-Z0-9_]+', '_', 'g')) || '_' || id::text
WHERE username IS NULL;


-- Additional staff document linking support
ALTER TABLE irp5_documents ALTER COLUMN employee_user_id DROP NOT NULL;
ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS document_type VARCHAR(40) NULL DEFAULT 'IRP5';
ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS target_staff_type VARCHAR(40) NULL DEFAULT 'employee';
ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS target_staff_id INTEGER NULL;
UPDATE irp5_documents SET document_type = COALESCE(document_type, 'IRP5');
UPDATE irp5_documents SET target_staff_type = COALESCE(target_staff_type, 'employee');
UPDATE irp5_documents SET target_staff_id = COALESCE(target_staff_id, employee_user_id);
