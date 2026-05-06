-- Safe franchise website database fix. Safe to run repeatedly.
ALTER TABLE franchise_registrations
ADD COLUMN IF NOT EXISTS website VARCHAR(500);

ALTER TABLE franchise_users
ADD COLUMN IF NOT EXISTS website VARCHAR(500);

UPDATE franchise_registrations
SET website = 'https://' || website
WHERE website IS NOT NULL
  AND website <> ''
  AND website NOT ILIKE 'http://%'
  AND website NOT ILIKE 'https://%';

UPDATE franchise_users
SET website = 'https://' || website
WHERE website IS NOT NULL
  AND website <> ''
  AND website NOT ILIKE 'http://%'
  AND website NOT ILIKE 'https://%';

-- Copy approved registration website to the live franchise profile where email matches.
UPDATE franchise_users fu
SET website = fr.website
FROM users u
JOIN franchise_registrations fr ON LOWER(fr.email) = LOWER(u.email)
WHERE fu.user_id = u.id
  AND fr.website IS NOT NULL
  AND fr.website <> ''
  AND (fu.website IS NULL OR fu.website = '');
