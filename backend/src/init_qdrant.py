# src/init_qdrant.py
from qdrant_client.http import models
from config.database import qdrant_client

COLLECTION_NAME = "financial_chatbot_news"

try:
    if qdrant_client.collection_exists(COLLECTION_NAME):
        print(f"Deleting existing collection '{COLLECTION_NAME}'...")
        qdrant_client.delete_collection(COLLECTION_NAME)
except Exception as e:
    print(f"Error checking/deleting collection: {e}")

print(f"Recreating collection '{COLLECTION_NAME}' with 768-dimensional dense vectors...")
try:
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=768,  # Size of 'all-mpnet-base-v2' vector embeddings
            distance=models.Distance.COSINE
        )
    )
    print("Collection created successfully on Qdrant Cloud!")
except Exception as e:
    print(f"Error creating collection: {e}")