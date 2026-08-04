import os
from sqlalchemy import text
from dotenv import load_dotenv
from config.database import engine

load_dotenv()

def seed_database():
    print("--- Connecting to Neon Postgres to seed data ---")
    
    # 1. Default Sectors
    sectors = [
        {"name": "Technology", "parent_sector_id": None},
        {"name": "Banking & Financial Services", "parent_sector_id": None},
        {"name": "Automotive", "parent_sector_id": None},
        {"name": "Energy & Power", "parent_sector_id": None},
        {"name": "Pharmaceuticals & Healthcare", "parent_sector_id": None},
    ]

    # 2. Default Companies linked to Sectors
    # We will resolve sector IDs dynamically during insert
    companies = [
        {"name": "Reliance Industries Limited", "ticker": "RELIANCE", "sector": "Energy & Power"},
        {"name": "Tata Consultancy Services", "ticker": "TCS", "sector": "Technology"},
        {"name": "HDFC Bank Limited", "ticker": "HDFCBANK", "sector": "Banking & Financial Services"},
        {"name": "Infosys Limited", "ticker": "INFY", "sector": "Technology"},
        {"name": "Tata Motors Limited", "ticker": "TATAMOTORS", "sector": "Automotive"},
        {"name": "Ather Energy", "ticker": "ATHER", "sector": "Automotive"},
        {"name": "Aditya Infotech", "ticker": "ADITYA", "sector": "Technology"},
        {"name": "State Bank of India", "ticker": "SBIN", "sector": "Banking & Financial Services"},
        {"name": "SBI", "ticker": "SBI", "sector": "Banking & Financial Services"},
        {"name": "HDFC Bank Limited", "ticker": "HDFCBANK", "sector": "Banking & Financial Services"},
        {"name": "HDFC", "ticker": "HDFC", "sector": "Banking & Financial Services"},
        {"name": "ICICI Bank Limited", "ticker": "ICICIBANK", "sector": "Banking & Financial Services"},
        {"name": "ICICI", "ticker": "ICICI", "sector": "Banking & Financial Services"}
    ]

    try:
        with engine.connect() as connection:
            # Seed Sectors
            for sector in sectors:
                connection.execute(
                    text("""
                    INSERT INTO sectors (name, parent_sector_id)
                    VALUES (:name, :parent_sector_id)
                    ON CONFLICT (name) DO NOTHING
                    """),
                    sector
                )
            
            # Seed Companies
            for company in companies:
                connection.execute(
                    text("""
                    INSERT INTO companies (name, ticker, sector_id)
                    VALUES (
                        :name, 
                        :ticker, 
                        (SELECT id FROM sectors WHERE name = :sector)
                    )
                    ON CONFLICT (ticker) DO NOTHING
                    """),
                    company
                )
                
            connection.commit()
            print("Database seeded successfully with initial Sectors and Companies!")
            
    except Exception as e:
        print(f"Error seeding database: {e}")

if __name__ == "__main__":
    seed_database()
