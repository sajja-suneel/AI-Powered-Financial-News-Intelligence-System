# src/graph/state.py
from typing import TypedDict, List, Dict, Any, Optional

class CleanedArticle(TypedDict):
    """Cleaned article structure processed by the Ingestion Agent."""
    title: str
    content: str
    source: str
    published_at: str
    url: str

class AgentState(TypedDict):
    """
    Defines the shared memory state of the LangGraph Multi-Agent pipeline.
    """
    # 1. Raw Data Input (passed when invoking the graph)
    raw_input: Dict[str, Any]
    
    # 2. Cleaned and Validated Article (populated by Ingestion Agent)
    cleaned_article: Optional[CleanedArticle]
    
    # 3. Deduplication status (populated by Deduplication Agent)
    is_duplicate: bool
    duplicate_of_id: Optional[str]
    similarity_score: float
    
    # 4. Structured Data (populated by Entity Extraction Agent)
    entities: List[Dict[str, Any]]       # e.g., [{"name": "HDFC Bank", "category": "Company"}]
    
    # 5. Stock Impact Mappings (populated by Stock Impact Agent)
    impacted_stocks: List[Dict[str, Any]] # e.g., [{"symbol": "HDFCBANK", "confidence": 1.0, "sentiment": "positive"}]
    
    # 6. Metadata and logs
    article_id: Optional[str]
    errors: List[str]