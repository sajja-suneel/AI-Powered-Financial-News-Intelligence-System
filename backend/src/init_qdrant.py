# src/init_qdrant.py
from qdrant_client.http import models
from config.database import qdrant_client

COLLECTION_NAME = "financial_news"

def init_qdrant_collection():
    # 1. Fetch existing collections
    collections = qdrant_client.get_collections().collections
    exists = any(c.name == COLLECTION_NAME for c in collections)
    
    if exists:
        print(f"Collection '{COLLECTION_NAME}' already exists on Qdrant Cloud.")
        return

    print(f"Creating Qdrant collection: '{COLLECTION_NAME}'...")
    
    # 2. Create the collection with 384 dimensions (for sentence-transformers)
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=384,  # Size of 'all-MiniLM-L6-v2' vector embeddings
            distance=models.Distance.COSINE
        )
    )
    print("Collection created successfully on Qdrant Cloud!")

if __name__ == "__main__":
    init_qdrant_collection()