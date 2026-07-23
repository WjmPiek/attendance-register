-- Safe to run repeatedly.
ALTER TABLE franchise_users
ADD COLUMN IF NOT EXISTS website VARCHAR(500);

ALTER TABLE franchise_registrations
ADD COLUMN IF NOT EXISTS website VARCHAR(500);

-- These are optional; some database versions may already have them.
ALTER TABLE franchise_users
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;

ALTER TABLE franchise_registrations
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;

-- Normalise existing websites so staff ID QR codes open correctly.
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
