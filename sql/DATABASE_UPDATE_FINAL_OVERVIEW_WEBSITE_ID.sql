-- Final patch: franchise website registration + staff ID QR website target
ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS website VARCHAR(500);
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(500);
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS business_name VARCHAR(255);
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS trading_as VARCHAR(255);
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS business_registration_number VARCHAR(100);
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS vat_number VARCHAR(100);
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS office_address TEXT;
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS office_number VARCHAR(50);
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS twenty_four_hour_number VARCHAR(50);
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50);
ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
