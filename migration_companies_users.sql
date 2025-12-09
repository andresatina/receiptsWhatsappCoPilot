-- Migration: Add Companies and Users tables
-- This allows multiple users per company with separate Google Sheets

-- 1. Create companies table
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    business_name VARCHAR(255) NOT NULL,
    default_currency VARCHAR(10) DEFAULT 'USD',
    default_language VARCHAR(10) DEFAULT 'en',
    google_sheet_id VARCHAR(255),
    google_drive_folder_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Create users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255),
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Create default Test Company
INSERT INTO companies (id, business_name, default_currency, default_language, google_sheet_id, google_drive_folder_id)
VALUES (1, 'Test Company', 'USD', 'en', NULL, NULL)
ON CONFLICT DO NOTHING;

-- 4. Add company_id to existing tables (migration path)
-- This allows gradual migration from clients to companies

ALTER TABLE categories 
ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE;

ALTER TABLE cost_centers 
ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE;

ALTER TABLE patterns 
ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE;

-- 5. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone_number);
CREATE INDEX IF NOT EXISTS idx_users_company ON users(company_id);
CREATE INDEX IF NOT EXISTS idx_categories_company ON categories(company_id);
CREATE INDEX IF NOT EXISTS idx_cost_centers_company ON cost_centers(company_id);
CREATE INDEX IF NOT EXISTS idx_patterns_company ON patterns(company_id);

-- 6. Migration helper: Move existing clients data to companies
-- Run this ONLY if you want to migrate existing test data
-- INSERT INTO companies (business_name, default_currency, default_language)
-- SELECT DISTINCT 
--     COALESCE(business_name, 'User ' || phone_number) as business_name,
--     'USD' as default_currency,
--     'en' as default_language
-- FROM clients;

-- 7. Migration helper: Create users from existing clients
-- Run this ONLY if you want to migrate existing test data
-- INSERT INTO users (phone_number, name, company_id)
-- SELECT 
--     c.phone_number,
--     c.business_name,
--     comp.id
-- FROM clients c
-- JOIN companies comp ON COALESCE(c.business_name, 'User ' || c.phone_number) = comp.business_name;

-- 8. Migration helper: Update foreign keys in existing tables
-- Run this ONLY after step 7 is complete
-- UPDATE categories cat
-- SET company_id = u.company_id
-- FROM users u
-- WHERE cat.client_id = u.phone_number;

-- UPDATE cost_centers cc
-- SET company_id = u.company_id
-- FROM users u
-- WHERE cc.client_id = u.phone_number;

-- UPDATE patterns p
-- SET company_id = u.company_id
-- FROM users u
-- WHERE p.client_id = u.phone_number;

-- NOTES:
-- - Steps 6-8 are commented out - only run if you want to migrate existing data
-- - For fresh start, just run steps 1-5
-- - After migration is complete and tested, you can drop the old 'clients' table
-- - Don't forget to update database_handler.py to use companies/users tables
