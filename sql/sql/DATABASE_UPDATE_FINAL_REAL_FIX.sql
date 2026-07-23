-- Run in DBeaver before testing this patch
ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS website VARCHAR(500);
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(500);
ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique ON users (LOWER(username)) WHERE username IS NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL;
ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL;
ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL;
ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL;
