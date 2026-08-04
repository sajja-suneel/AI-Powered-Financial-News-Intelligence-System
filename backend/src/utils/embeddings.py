# src/utils/embeddings.py
from sentence_transformers import SentenceTransformer
from src.utils.logger import get_logger

logger = get_logger("utils.embeddings")

class EmbeddingEngine:
    """
    Manages loading, caching, and serving the SentenceTransformer embedding model.
    Implements a clean class-level Singleton pattern.
    """
    _model_instance = None
    MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"

    @classmethod
    def get_model(cls) -> SentenceTransformer:
        """
        Retrieves the cached embedding model instance, loading it on the first call.
        """
        if cls._model_instance is None:
            logger.info(f"[EMBEDDINGS] Loading '{cls.MODEL_NAME}' model into memory...")
            # Load the lightweight, fast 768-dimensional embedding model
            cls._model_instance = SentenceTransformer(cls.MODEL_NAME)
            logger.info("[EMBEDDINGS] Model loaded successfully.")
        return cls._model_instance

# ----------------------------------------------------
# Module-level alias to keep other files backward-compatible
# ----------------------------------------------------
get_embedding_model = EmbeddingEngine.get_model
