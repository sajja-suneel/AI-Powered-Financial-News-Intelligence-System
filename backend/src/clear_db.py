# src/clear_db.py
from sqlalchemy import text
from qdrant_client import models  # <-- IMPORT MODELS DIRECTLY FROM LIBRARY
from config.database import SessionLocal, qdrant_client

COLLECTION_NAME = "financial_chatbot_news"

def reset_databases():
    print("--- RESETTING DATABASES ---")
    
    # 1. Clear Neon PostgreSQL Tables
    db = SessionLocal()
    try:
        print("Clearing tables in Neon...")
        db.execute(text("TRUNCATE TABLE stock_impacts CASCADE;"))
        db.execute(text("TRUNCATE TABLE article_entities CASCADE;"))
        db.execute(text("TRUNCATE TABLE entities CASCADE;"))
        db.execute(text("TRUNCATE TABLE articles CASCADE;"))
        db.commit()
        print("Neon tables cleared successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error clearing Neon: {e}")
    finally:
        db.close()

    # 2. Clear Qdrant Cloud Collection Points
    try:
        print("Clearing points in Qdrant Cloud...")
        # Use the directly imported models module
        qdrant_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.Filter()
        )
        print("Qdrant points cleared successfully.")
    except Exception as e:
        print(f"Error clearing Qdrant: {e}")
        
    print("\n--- RESET COMPLETE. READY FOR FRESH INGESTION ---")

if __name__ == "__main__":
    reset_databases()