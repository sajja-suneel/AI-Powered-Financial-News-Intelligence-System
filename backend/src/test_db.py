# src/test_db.py
from sqlalchemy import text
from config.database import SessionLocal, qdrant_client
from qdrant_client.http import models
import uuid

def test_neon_connection():
    print("--- 1. Testing Neon PostgreSQL Connection ---")
    db = SessionLocal()
    try:
        # Check if we can connect and read tables
        result = db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public';")).fetchall()
        print("Connected to Neon successfully! Available tables:")
        for r in result:
            print(f" - {r[0]}")
            
        # Try a test insert
        test_id = uuid.uuid4()
        db.execute(
            text("""
            INSERT INTO articles (id, title, content, source, published_at, is_duplicate)
            VALUES (:id, 'Test Ingestion', 'This is a test article to verify database writes.', 'Test', NOW(), false)
            """),
            {"id": test_id}
        )
        db.commit()
        print(f"Success! Inserted test article (ID: {test_id}) into Neon.")
        
        # Clean up test article
        db.execute(text("DELETE FROM articles WHERE id = :id"), {"id": test_id})
        db.commit()
        print("Cleaned up test article from Neon.")
        
    except Exception as e:
        print(f"\n[NEON CONNECTION ERROR]: {e}")
        print("Double-check your DATABASE_URL in the .env file.")
    finally:
        db.close()

def test_qdrant_connection():
    print("\n--- 2. Testing Qdrant Cloud Connection ---")
    COLLECTION_NAME = "financial_chatbot_news"
    try:
        # Check if we can fetch collections
        collections = qdrant_client.get_collections().collections
        print("Connected to Qdrant Cloud successfully! Available collections:")
        for col in collections:
            print(f" - {col.name}")
            
        # Try a test point upsert
        test_id = str(uuid.uuid4())
        # Mock vector (768 dimensions filled with 0.1)
        mock_vector = [0.1] * 768
        
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                models.PointStruct(
                    id=test_id,
                    vector=mock_vector,
                    payload={"title": "Test Point"}
                )
            ]
        )
        print(f"Success! Upserted test point (ID: {test_id}) to Qdrant Cloud.")
        
        # Clean up test point
        qdrant_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.PointIdsList(points=[test_id])
        )
        print("Cleaned up test point from Qdrant Cloud.")
        
    except Exception as e:
        print(f"\n[QDRANT CONNECTION ERROR]: {e}")
        print("Double-check your QDRANT_HOST and QDRANT_API_KEY in the .env file.")

if __name__ == "__main__":
    test_neon_connection()
    test_qdrant_connection()