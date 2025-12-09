-- Database Schema for Receipt Processing Agent
-- Run this in your PostgreSQL database

-- Clients table
CREATE TABLE clients (
    phone_number VARCHAR(20) PRIMARY KEY,
    business_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Categories (Chart of Accounts) - built dynamically per client
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(20) REFERENCES clients(phone_number) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, name)  -- Prevent duplicate categories per client
);

-- Cost Centers (properties, units, departments, etc.)
CREATE TABLE cost_centers (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(20) REFERENCES clients(phone_number) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, name)  -- Prevent duplicate cost centers per client
);

-- Merchant-Item Patterns for learning
CREATE TABLE patterns (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(20) REFERENCES clients(phone_number) ON DELETE CASCADE,
    merchant VARCHAR(255) NOT NULL,
    items_keywords TEXT[],  -- Array of keywords extracted from items
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    cost_center_id INTEGER REFERENCES cost_centers(id) ON DELETE CASCADE,
    frequency INTEGER DEFAULT 1,  -- How many times this pattern used
    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, merchant, category_id, cost_center_id)  -- One pattern per merchant+category+cost_center combo
);

-- Index for faster pattern lookups
CREATE INDEX idx_patterns_client_merchant ON patterns(client_id, merchant);
CREATE INDEX idx_patterns_keywords ON patterns USING GIN(items_keywords);

-- Optional: Business rules (free text rules from users)
CREATE TABLE business_rules (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(20) REFERENCES clients(phone_number) ON DELETE CASCADE,
    rule_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
