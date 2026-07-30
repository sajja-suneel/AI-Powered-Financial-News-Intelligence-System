# src/utils/embeddings.py
from sentence_transformers import SentenceTransformer

# Global cache for the embedding model
_model_instance = None

def get_embedding_model() -> SentenceTransformer:
    """
    Singleton loader for the local sentence-transformer model.
    Downloads the model on the first run and caches it in memory.
    """
    global _model_instance
    if _model_instance is None:
        print("\n[EMBEDDINGS] Loading 'all-MiniLM-L6-v2' model into memory...")
        # Load the lightweight, fast 384-dimensional embedding model
        _model_instance = SentenceTransformer("all-MiniLM-L6-v2")
        print("[EMBEDDINGS] Model loaded successfully.")
    return _model_instance