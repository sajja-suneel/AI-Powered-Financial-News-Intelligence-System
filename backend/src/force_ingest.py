# src/force_ingest.py
import asyncio
from src.graph.workflow import app as master_graph

def force_ingest_test():
    print("--- FORCING TEST INGESTION ---")
    
    # 1. Mock raw article data
    test_state = {
        "raw_input": {
            "title": "State Bank of India shares close higher on strong earnings",
            "content": "Shares of State Bank of India (SBI) closed higher today as traders responded positively to the recent profit reporting. The overall banking sector was up.",
            "source": "Exchanges",
            "published_at": "Today",
            "url": "https://www.bseindia.com"
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
    
    # 2. Run it through the sequential graph
    result = master_graph.invoke(test_state)
    
    print("\n--- INGESTION RESULT ---")
    if result.get("errors"):
        print(f"FAILED! Errors logged during execution: {result['errors']}")
    else:
        print(f"SUCCESS! Article ID generated: {result.get('article_id')}")
        print(f"Is Duplicate: {result.get('is_duplicate')}")

if __name__ == "__main__":
    force_ingest_test()