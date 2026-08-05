# src/utils/mongodb_history.py
import os
from datetime import datetime
from config.database import mongo_db
from src.utils.logger import get_logger

logger = get_logger("utils.mongodb_history")

# Get collection name dynamically from env, default to 'chat_history'
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "chat_history")

class MongoChatHistory:
    """
    Helper class to manage session-based chat history storage in MongoDB.
    """
    
    @staticmethod
    def get_history(session_id: str, limit: int = 5) -> list:
        """
        Loads the last `limit` turns of query transcripts from MongoDB for a session.
        """
        if mongo_db is None:
            logger.warning("[MONGODB] Client is not initialized. Returning empty history.")
            return []
            
        try:
            history_cursor = mongo_db[MONGO_COLLECTION].find(
                {"session_id": session_id}
            ).sort("timestamp", -1).limit(limit)
            history = list(history_cursor)
            history.reverse()  # Chronological order
            return history
        except Exception as e:
            logger.error(f"[MONGODB ERROR] Failed to load chat history for session {session_id}: {e}")
            return []

    @staticmethod
    def save_turn(session_id: str, query: str, reformulated_query: str, explanation: str):
        """
        Saves a single conversation turn (query and response) into MongoDB.
        """
        if mongo_db is None:
            logger.warning("[MONGODB] Client is not initialized. Turn not saved.")
            return
            
        try:
            mongo_db[MONGO_COLLECTION].insert_one({
                "session_id": session_id,
                "query": query,
                "reformulated_query": reformulated_query,
                "explanation": explanation,
                "timestamp": datetime.utcnow()
            })
            logger.info(f"[MONGODB] Saved turn for session: {session_id}")
        except Exception as e:
            logger.error(f"[MONGODB ERROR] Failed to save turn for session {session_id}: {e}")
