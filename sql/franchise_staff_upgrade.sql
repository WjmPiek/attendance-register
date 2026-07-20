-- Franchise-owned manager and employee creation

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
CREATE INDEX IF NOT EXISTS idx_employee_users_employee_role ON employee_users(employee_role);

-- Optional hardening for office/GPS assignments used by the HR staff panel.
ALTER TABLE gps_allocations_per_user
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_gps_allocations_user_active ON gps_allocations_per_user(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_gps_allocations_area_id ON gps_allocations_per_user(area_id);
