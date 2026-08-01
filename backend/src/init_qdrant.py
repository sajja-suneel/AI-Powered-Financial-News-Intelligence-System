# src/init_qdrant.py
from qdrant_client.http import models
from config.database import qdrant_client

class QdrantInitializer:
    """
    Initializes semantic vector search collections on Qdrant Cloud.
    """
    COLLECTION_NAME = "financial_news"
    VECTOR_DIMENSIONS = 384  # Size of 'all-MiniLM-L6-v2' vector embeddings

    @staticmethod
    def run():
        # 1. Fetch existing collections
        collections = qdrant_client.get_collections().collections
        exists = any(c.name == QdrantInitializer.COLLECTION_NAME for c in collections)
        
        if exists:
            print(f"Collection '{QdrantInitializer.COLLECTION_NAME}' already exists on Qdrant Cloud.")
            return

        print(f"Creating Qdrant collection: '{QdrantInitializer.COLLECTION_NAME}'...")
        
        # 2. Create the collection config
        qdrant_client.create_collection(
            collection_name=QdrantInitializer.COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=QdrantInitializer.VECTOR_DIMENSIONS,
                distance=models.Distance.COSINE
            )
        )
        print("Collection created successfully on Qdrant Cloud!")

if __name__ == "__main__":
    QdrantInitializer.run()