CREATE TABLE IF NOT EXISTS franchise_registrations (
    id SERIAL PRIMARY KEY,

    business_name VARCHAR(255) NOT NULL,
    trading_as VARCHAR(255),
    business_registration_number VARCHAR(100),
    vat_number VARCHAR(100),
    office_address TEXT,
    office_number VARCHAR(50),
    twenty_four_hour_number VARCHAR(50),

    franchisee_name VARCHAR(120) NOT NULL,
    franchisee_surname VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    contact_number VARCHAR(50),
    password_hash VARCHAR(255),

    status VARCHAR(30) DEFAULT 'pending',
    approved_by_user_id INT,
    approved_at TIMESTAMP,
    rejected_reason TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS approved_by_user_id INT;
ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP;
ALTER TABLE franchise_registrations ADD COLUMN IF NOT EXISTS rejected_reason TEXT;
