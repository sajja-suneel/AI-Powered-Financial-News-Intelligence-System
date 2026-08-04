# src/agents/deduplication.py
import uuid
from src.graph.state import AgentState
from src.utils.embeddings import get_embedding_model
from src.utils.logger import get_logger
from config.database import qdrant_client

logger = get_logger("agent.deduplication")

class DeduplicationAgent:
    """
    Evaluates incoming cleaned articles for uniqueness by executing semantic vector searches
    on Qdrant Cloud and detecting duplicates using cosine similarity scores.
    """
    COLLECTION_NAME = "financial_chatbot_news"
    SIMILARITY_THRESHOLD = 0.90

    @staticmethod
    def check_uniqueness(state: AgentState) -> AgentState:
        """
        LangGraph Node function that generates vector embeddings of the article content,
        compares it against Qdrant, and sets duplication flags on the state.
        """
        if state.get("errors"):
            return state
            
        article = state.get("cleaned_article")
        if not article:
            state["errors"].append("Deduplicator: No cleaned article found in state.")
            return state
            
        logger.info(f"[SUBAGENT] Deduplicator: Checking uniqueness for '{article['title']}'...")
        
        try:
            # 1. Retrieve the cached singleton embedding model
            model = get_embedding_model()
            
            # 2. Generate dense vector embedding from the article content
            vector = model.encode(article["content"]).tolist()
            
            # 3. Search Qdrant Cloud for matching vectors above the 0.90 threshold
            search_res = qdrant_client.query_points(
                collection_name=DeduplicationAgent.COLLECTION_NAME,
                query=vector,
                limit=1,
                score_threshold=DeduplicationAgent.SIMILARITY_THRESHOLD
            )
            
            # 4. Populate duplicate parameters inside the shared state
            if search_res.points:
                match = search_res.points[0]
                state["is_duplicate"] = True
                state["duplicate_of_id"] = match.payload.get("article_id")
                state["similarity_score"] = float(match.score)
                logger.info(f"--> DUPLICATE found. Match Score: {match.score:.2f} (Linked to ID: {state['duplicate_of_id']})")
            else:
                state["is_duplicate"] = False
                state["duplicate_of_id"] = None
                state["similarity_score"] = 0.0
                logger.info("--> Article is UNIQUE.")
                
        except Exception as e:
            logger.error(f"Deduplication Error: {e}")
            state["errors"].append(f"Deduplicator: {str(e)}")
            
        return state

# ----------------------------------------------------
# Module-level alias to keep other files backward-compatible
# ----------------------------------------------------
deduplication_subagent = DeduplicationAgent.check_uniqueness