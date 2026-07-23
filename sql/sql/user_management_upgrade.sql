-- User management + franchise approval auto-create support

ALTER TABLE franchise_registrations
ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255),
ADD COLUMN IF NOT EXISTS approved_by_user_id INT,
ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS rejected_reason TEXT,
ADD COLUMN IF NOT EXISTS manager_note TEXT;

ALTER TABLE franchise_users
ADD COLUMN IF NOT EXISTS business_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS trading_as VARCHAR(255),
ADD COLUMN IF NOT EXISTS business_registration_number VARCHAR(100),
ADD COLUMN IF NOT EXISTS vat_number VARCHAR(100),
ADD COLUMN IF NOT EXISTS office_address TEXT,
ADD COLUMN IF NOT EXISTS office_number VARCHAR(50),
ADD COLUMN IF NOT EXISTS twenty_four_hour_number VARCHAR(50),
ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50),
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

ALTER TABLE manager_users
ADD COLUMN IF NOT EXISTS franchise_user_id INT,
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

ALTER TABLE employee_users
ADD COLUMN IF NOT EXISTS franchise_user_id INT,
ADD COLUMN IF NOT EXISTS manager_user_id INT,
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_franchise_registrations_status ON franchise_registrations(status);
CREATE INDEX IF NOT EXISTS idx_manager_users_franchise_user_id ON manager_users(franchise_user_id);
CREATE INDEX IF NOT EXISTS idx_employee_users_franchise_user_id ON employee_users(franchise_user_id);
CREATE INDEX IF NOT EXISTS idx_employee_users_manager_user_id ON employee_users(manager_user_id);
