import json
import asyncio
from src.graph.workflow import app

def run_news_ingestion():
    # Load your scraped RBI data
    with open("data/mock_dataset.json", "r", encoding="utf-8") as f:
        articles = json.load(f)
        
    print(f"Loaded {len(articles)} articles from raw cache.")
    
    # Process each article through the LangGraph agents
    for idx, art in enumerate(articles):
        print(f"\n======================================")
        print(f"Processing Article {idx+1}: {art['title']}")
        
        # Define initial state
        initial_state = {
            "title": art["title"],
            "content": art["content"],
            "source": art["source"],
            "published_at": art.get("published_at", "Today"),
            "url": art["url"],
            "is_duplicate": False,
            "duplicate_of_id": None,
            "similarity_score": 0.0,
            "entities": [],
            "impacted_stocks": [],
            "article_id": None,
            "errors": []
        }
        
        # Invoke the LangGraph pipeline
        result = app.invoke(initial_state)
        print(f"Finished processing Article {idx+1}!")

if __name__ == "__main__":
    run_news_ingestion()