-- Safe fix for franchise website save/edit and Staff ID QR website source

ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS website VARCHAR(500) NULL;
ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(500) NULL;
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;

-- Normalize existing websites.
UPDATE franchise_users
SET website = 'https://' || website
WHERE website IS NOT NULL
  AND website <> ''
  AND website NOT ILIKE 'http://%'
  AND website NOT ILIKE 'https://%';

UPDATE franchise_registrations
SET website = 'https://' || website
WHERE website IS NOT NULL
  AND website <> ''
  AND website NOT ILIKE 'http://%'
  AND website NOT ILIKE 'https://%';

-- Sync existing registration website values to live franchise profiles by email.
UPDATE franchise_users fu
SET website = fr.website,
    updated_at = NOW()
FROM users u
JOIN franchise_registrations fr ON LOWER(fr.email) = LOWER(u.email)
WHERE fu.user_id = u.id
  AND fr.website IS NOT NULL
  AND fr.website <> ''
  AND (fu.website IS NULL OR fu.website = '');
