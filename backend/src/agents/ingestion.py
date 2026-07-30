# src/agents/ingestion.py
from src.graph.state import AgentState

# 1. Ingestion Agent Graph Node (No changes here)
def ingestion_subagent(state: AgentState) -> AgentState:
    print("\n[SUBAGENT] Ingestion: Validating and cleaning raw input...")
    raw = state.get("raw_input", {})
    
    title = raw.get("title")
    content = raw.get("content")
    
    if not title or not content:
        print("[INGESTION ERROR] Article title or content is missing.")
        state["errors"].append("Ingestion Agent: Missing required 'title' or 'content' fields.")
        return state
        
    state["cleaned_article"] = {
        "title": title.strip(),
        "content": content.strip(),
        "source": raw.get("source", "Unknown Source"),
        "published_at": raw.get("published_at", "Today"),
        "url": raw.get("url", "")
    }
    
    print(f"--> Ingestion complete. Cleaned: '{state['cleaned_article']['title']}'")
    return state


# 2. Bulk File Ingestion Runner Helper
def ingest_raw_news_file(file_path: str, source_label: str):
    """
    Reads local JSON raw data lists and passes them into the Ingestion Agent.
    """
    # ─── LOCAL IMPORT TO BREAK THE CIRCULAR DEPENDENCY LOOP ───
    from src.graph.workflow import app as master_graph
    
    import json
    import os
    
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return
        
    with open(file_path, "r", encoding="utf-8") as f:
        articles = json.load(f)
        
    print(f"Ingesting {len(articles)} articles from {source_label}...")
    for idx, art in enumerate(articles):
        initial_state = {
            "raw_input": {
                "title": art["title"],
                "content": art["content"],
                "source": source_label,
                "published_at": art.get("published_at", "Today"),
                "url": art.get("url", "")
            },
            "cleaned_article": None,
            "is_duplicate": False,
            "duplicate_of_id": None,
            "similarity_score": 0.0,
            "entities": [],
            "impacted_stocks": [],
            "article_id": None,
            "errors": []
        }
        master_graph.invoke(initial_state)