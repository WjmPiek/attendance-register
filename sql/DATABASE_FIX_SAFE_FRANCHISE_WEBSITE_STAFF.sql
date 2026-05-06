-- Safe to run multiple times in DBeaver
ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique ON users(username) WHERE username IS NOT NULL AND username <> '';
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(255);
ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS website VARCHAR(255);
ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS manager_note TEXT;
ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL;
ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL;
ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL;
ALTER TABLE employee_users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_mime VARCHAR(80) NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_filename VARCHAR(255) NULL;
UPDATE franchise_users SET website = 'https://' || website WHERE website IS NOT NULL AND website <> '' AND website NOT ILIKE 'http://%' AND website NOT ILIKE 'https://%';
UPDATE franchise_registrations SET website = 'https://' || website WHERE website IS NOT NULL AND website <> '' AND website NOT ILIKE 'http://%' AND website NOT ILIKE 'https://%';
