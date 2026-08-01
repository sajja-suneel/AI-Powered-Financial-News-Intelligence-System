# src/agents/storage.py
import uuid
from sqlalchemy import text
from src.graph.state import AgentState
from src.utils.embeddings import get_embedding_model
from src.utils.logger import get_logger
from config.database import SessionLocal, qdrant_client
from qdrant_client.http import models

logger = get_logger("agent.storage")

class StorageAgent:
    """
    Finalizes the news ingestion workflow by saving relational metadata to Neon PostgreSQL
    and upserting dense vector embeddings to Qdrant Cloud.
    """
    COLLECTION_NAME = "financial_news"

    @staticmethod
    def save_to_databases(state: AgentState) -> AgentState:
        """
        LangGraph Node function that writes article details, entities, and impacts to
        PostgreSQL and Qdrant.
        """
        logger.info("[SUBAGENT] Finalizer: Saving state...")
        
        article = state.get("cleaned_article")
        if not article:
            state["errors"].append("Finalizer: No cleaned article found in state.")
            return state
            
        db = SessionLocal()
        article_id = uuid.uuid4()
        state["article_id"] = article_id
        
        # 1. Neon PostgreSQL Transaction (Relational SQL Data)
        try:
            # Save core article fields
            db.execute(
                text("""
                INSERT INTO articles (id, title, content, source, published_at, is_duplicate, duplicate_of_id)
                VALUES (:id, :title, :content, :source, :published_at, :is_duplicate, :duplicate_of_id)
                """),
                {
                    "id": article_id,
                    "title": article["title"],
                    "content": article["content"],
                    "source": article["source"],
                    "published_at": article["published_at"],
                    "is_duplicate": state["is_duplicate"],
                    "duplicate_of_id": state["duplicate_of_id"]
                }
            )
            
            # Save stock impact mapping metadata (Only if unique)
            if not state["is_duplicate"]:
                for impact in state["impacted_stocks"]:
                    db.execute(
                        text("""
                        INSERT INTO stock_impacts (article_id, company_id, confidence_score, impact_type, sentiment, reasoning)
                        SELECT :aid, id, :score, :type, :sentiment, :reasoning FROM companies WHERE ticker = :ticker
                        """),
                        {
                            "aid": article_id,
                            "score": impact["confidence"],
                            "type": impact["type"],
                            "sentiment": impact["sentiment"],
                            "reasoning": impact["reasoning"],
                            "ticker": impact["symbol"]
                        }
                    )
                    
            db.commit()
            logger.info("--> Saved to Neon Database successfully.")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Postgres Storage Error: {e}")
            state["errors"].append(f"Storage Postgres: {str(e)}")
            return state
        finally:
            db.close()
            
        # 2. Qdrant Cloud Vector Indexing (Only if unique)
        if not state["is_duplicate"]:
            try:
                # Retrieve cached singleton embedding model
                model = get_embedding_model()
                
                # Generate sentence embedding vector locally
                vector = model.encode(article["content"]).tolist()
                
                payload = {
                    "article_id": str(article_id),
                    "title": article["title"],
                    "sectors": [ent["name"] for ent in state["entities"] if ent["category"] == "Sector"],
                    "companies": [ent["name"] for ent in state["entities"] if ent["category"] == "Company"]
                }
                
                # Upsert vector point to Qdrant Cloud
                qdrant_client.upsert(
                    collection_name=StorageAgent.COLLECTION_NAME,
                    points=[
                        models.PointStruct(
                            id=str(article_id),
                            vector=vector,
                            payload=payload
                        )
                    ]
                )
                logger.info("--> Indexed in Qdrant Cloud successfully.")
                
            except Exception as e:
                logger.error(f"Qdrant Index Error: {e}")
                state["errors"].append(f"Storage Qdrant: {str(e)}")
                
        return state

# ----------------------------------------------------
# Module-level alias to keep other files backward-compatible
# ----------------------------------------------------
finalizer_subagent = StorageAgent.save_to_databases