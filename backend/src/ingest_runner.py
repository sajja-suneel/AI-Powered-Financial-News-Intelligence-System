# src/ingest_runner.py
import json
import os

# 1. Import the compiled LangGraph workflow
from src.graph.workflow import app as master_graph

def connect_json_to_agents(json_file_path: str, source_label: str):
    """
    Reads the raw JSON file and feeds each article into the LangGraph multi-agent pipeline.
    """
    print(f"\n--- Starting Ingestion: {source_label} ---")
    
    # Check if the raw data file exists
    if not os.path.exists(json_file_path):
        print(f"Error: Raw JSON file not found at {json_file_path}")
        return

    # 2. Read the JSON file into a Python list
    with open(json_file_path, "r", encoding="utf-8") as f:
        raw_articles = json.load(f)
        
    print(f"Successfully loaded {len(raw_articles)} raw articles from {json_file_path}.")

    # 3. Loop through each article in the JSON array
    for idx, raw_art in enumerate(raw_articles):
        print(f"\nIngesting article [{idx+1}/{len(raw_articles)}]: '{raw_art.get('title')}'")
        
        # 4. Package the raw article into the LangGraph state input schema
        # The raw JSON fields are mapped inside the 'raw_input' dictionary
        initial_state = {
            "raw_input": {
                "title": raw_art.get("title"),
                "content": raw_art.get("content"),
                "source": source_label,
                "published_at": raw_art.get("published_at", "Today"),
                "url": raw_art.get("url", "")
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
        
        # 5. Invoke the Master LangGraph app
        # This triggers the sequential flow: Ingest -> Deduplicate -> Extract -> Impact -> Store
        result = master_graph.invoke(initial_state)
        
        # Check if the agent encountered any processing errors
        if result.get("errors"):
            print(f"--> Status: FAILED. Errors: {result['errors']}")
        else:
            print(f"--> Status: SUCCESS. Article ID: {result['article_id']} (Duplicate: {result['is_duplicate']})")

if __name__ == "__main__":
    # Test connection with RBI scraped data
    connect_json_to_agents("data/mock_dataset.json", "RBI")