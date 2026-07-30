# src/agents/deduplication.py
import uuid
from src.graph.state import AgentState
from src.utils.embeddings import get_embedding_model
from config.database import qdrant_client

model = get_embedding_model()
COLLECTION_NAME = "financial_news"

def deduplication_subagent(state: AgentState) -> AgentState:
    if state.get("errors"):
        return state
        
    article = state.get("cleaned_article")
    if not article:
        state["errors"].append("Deduplicator: No cleaned article found in state.")
        return state
        
    print(f"\n[SUBAGENT] Deduplicator: Checking uniqueness for '{article['title']}'...")
    
    try:
        # 1. Generate dense vector embedding from the article content
        vector = model.encode(article["content"]).tolist()
        
        # 2. Search Qdrant Cloud using current query_points method
        search_res = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,              # Uses 'query' instead of 'query_vector'
            limit=1,
            score_threshold=0.85
        )
        
        # 3. Populate duplicate parameters inside the shared state
        # In query_points, the results are stored in the '.points' attribute list
        if search_res.points:
            match = search_res.points[0]
            state["is_duplicate"] = True
            state["duplicate_of_id"] = match.payload.get("article_id")
            state["similarity_score"] = float(match.score)
            print(f"--> DUPLICATE found. Match Score: {match.score:.2f} (Linked to ID: {state['duplicate_of_id']})")
        else:
            state["is_duplicate"] = False
            state["duplicate_of_id"] = None
            state["similarity_score"] = 0.0
            print("--> Article is UNIQUE.")
            
    except Exception as e:
        print(f"Deduplication Error: {e}")
        state["errors"].append(f"Deduplicator: {str(e)}")
        
    return state