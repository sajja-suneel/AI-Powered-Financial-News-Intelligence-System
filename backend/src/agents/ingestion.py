# src/agents/ingestion.py
from src.graph.state import AgentState
from src.utils.logger import get_logger

logger = get_logger("agent.ingestion")

class IngestionAgent:
    """
    Manages raw news article validation, cleaning, and bulk file ingestion runners.
    """

    @staticmethod
    def clean_and_validate(state: AgentState) -> AgentState:
        """
        LangGraph Node function that validates and cleans incoming raw article inputs.
        """
        logger.info("[SUBAGENT] Ingestion: Validating and cleaning raw input...")
        raw = state.get("raw_input", {})
        
        title = raw.get("title")
        content = raw.get("content")
        
        if not title or not content:
            logger.error("[INGESTION ERROR] Article title or content is missing.")
            state["errors"].append("Ingestion Agent: Missing required 'title' or 'content' fields.")
            return state
            
        # Reject blocked or Access Denied pages from index ingestion
        blocked_keywords = ["access denied", "attention required", "cloudflare", "captcha", "security check", "forbidden"]
        content_lower = content.lower()
        title_lower = title.lower()
        if any(kw in content_lower for kw in blocked_keywords) or any(kw in title_lower for kw in blocked_keywords):
            logger.error(f"[INGESTION ERROR] Scraper was blocked by destination host: '{title}'.")
            state["errors"].append(f"Ingestion Agent: Scraper blocked or Access Denied page detected: '{title}'.")
            return state
            
        state["cleaned_article"] = {
            "title": title.strip(),
            "content": content.strip(),
            "source": raw.get("source", "Unknown Source"),
            "published_at": raw.get("published_at", "Today"),
            "url": raw.get("url", "")
        }
        
        logger.info(f"--> Ingestion complete. Cleaned: '{state['cleaned_article']['title']}'")
        return state


    @staticmethod
    def ingest_raw_file(file_path: str, source_label: str):
        """
        Reads local JSON raw data lists and passes them into the Ingestion Agent.
        """
        # ─── LOCAL IMPORT TO BREAK THE CIRCULAR DEPENDENCY LOOP ───
        from src.graph.workflow import app as master_graph
        
        import json
        import os
        
        if not os.path.exists(file_path):
            logger.error(f"Error: {file_path} not found.")
            return
            
        with open(file_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
            
        logger.info(f"Ingesting {len(articles)} articles from {source_label}...")
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

# ----------------------------------------------------
# Module-level aliases to keep other files backward-compatible
# ----------------------------------------------------
ingestion_subagent = IngestionAgent.clean_and_validate
ingest_raw_news_file = IngestionAgent.ingest_raw_file