-- Franchise scope fix

ALTER TABLE manager_users
ADD COLUMN IF NOT EXISTS franchise_user_id INT,
ADD COLUMN IF NOT EXISTS name VARCHAR(120),
ADD COLUMN IF NOT EXISTS surname VARCHAR(120),
ADD COLUMN IF NOT EXISTS email VARCHAR(255),
ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50),
ADD COLUMN IF NOT EXISTS office_address_assigned TEXT,
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

ALTER TABLE employee_users
ADD COLUMN IF NOT EXISTS franchise_user_id INT,
ADD COLUMN IF NOT EXISTS manager_user_id INT,
ADD COLUMN IF NOT EXISTS employee_role VARCHAR(80),
ADD COLUMN IF NOT EXISTS name VARCHAR(120),
ADD COLUMN IF NOT EXISTS surname VARCHAR(120),
ADD COLUMN IF NOT EXISTS email VARCHAR(255),
ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50),
ADD COLUMN IF NOT EXISTS office_address_assigned TEXT,
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_manager_users_franchise_user_id ON manager_users(franchise_user_id);
CREATE INDEX IF NOT EXISTS idx_employee_users_franchise_user_id ON employee_users(franchise_user_id);
CREATE INDEX IF NOT EXISTS idx_employee_users_manager_user_id ON employee_users(manager_user_id);

-- Backfill: if an existing FranchiseUser has employees/managers without franchise_user_id,
-- you can update them manually after confirming ownership.
-- Example:
-- UPDATE manager_users SET franchise_user_id = 1 WHERE user_id IN (...);
-- UPDATE employee_users SET franchise_user_id = 1 WHERE user_id IN (...);
