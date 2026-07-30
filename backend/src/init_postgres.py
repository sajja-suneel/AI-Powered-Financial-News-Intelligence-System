import os
from sqlalchemy import text
from dotenv import load_dotenv
from config.database import engine  # Import the engine we created in config

# Load .env variables
load_dotenv()

# The SQL schema wrapped inside a Python multi-line string
SQL_SCHEMA = """
-- 1. Create Sector Registry Table
CREATE TABLE IF NOT EXISTS sectors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    parent_sector_id INT REFERENCES sectors(id)
);

-- 2. Create Companies Table
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    ticker VARCHAR(20) UNIQUE NOT NULL,
    sector_id INT REFERENCES sectors(id)
);

-- 3. Create Articles Table
CREATE TABLE IF NOT EXISTS articles (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source VARCHAR(100),
    published_at TIMESTAMP WITH TIME ZONE,
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of_id UUID REFERENCES articles(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Create Entities Table
CREATE TABLE IF NOT EXISTS entities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    UNIQUE(name, category)
);

-- 5. Create Article-Entity Junction Table
CREATE TABLE IF NOT EXISTS article_entities (
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    entity_id INT REFERENCES entities(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, entity_id)
);

-- 6. Create Stock Impact Mapping Table
CREATE TABLE IF NOT EXISTS stock_impacts (
    id SERIAL PRIMARY KEY,
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    company_id INT REFERENCES companies(id) ON DELETE CASCADE,
    confidence_score NUMERIC(3, 2) NOT NULL,
    impact_type VARCHAR(50) NOT NULL,
    sentiment VARCHAR(20) NOT NULL,
    reasoning TEXT
);
"""

def initialize_database():
    print("--- Connecting to Neon Postgres to create tables ---")
    try:
        with engine.connect() as connection:
            # Execute the SQL commands
            connection.execute(text(SQL_SCHEMA))
            connection.commit()
            print("PostgreSQL tables created successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}")

if __name__ == "__main__":
    initialize_database()