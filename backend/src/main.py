# src/main.py
import sys
import asyncio

# Fix Windows ProactorEventLoop subprocess bug for Playwright/Crawl4AI
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn
import os
import json
import concurrent.futures
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

from src.agents.query_processor import execute_hybrid_search
from src.graph.workflow import app as agent_app
from src.utils.scraper import WebScraper  # Class-based scraper
from src.utils.logger import get_logger

logger = get_logger("api.main")

app = FastAPI(
    title="Tradl Financial News Intelligence API",
    description="Clean, self-contained REST API backend for context-aware financial intelligence."
)

# Enable CORS for external frontend applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------
# Request Validation Models
# ----------------------------------------------------
class ArticleIngest(BaseModel):
    title: str = Field(..., description="The headline of the article")
    content: str = Field(..., description="The full text body of the article")
    source: str = Field(..., description="The source name")
    published_at: Optional[str] = Field("Today", description="Date published")
    url: Optional[str] = Field("", description="URL link to the source article")

class UrlIngest(BaseModel):
    url: str = Field(..., description="The URL of the financial news page to scrape and ingest")

class ChatRequest(BaseModel):
    message: str = Field(..., description="The search query or chat message sent by the user")


# ----------------------------------------------------
# Class-Based Ingestion Helper (Refactored from functions)
# ----------------------------------------------------
class BulkIngester:
    """
    Manages loading raw scraped JSON files from disk and triggering
    the LangGraph agent pipeline to clean, deduplicate, and store the articles.
    """
    @staticmethod
    def ingest_from_file(filepath: str, default_source: str) -> int:
        """
        Reads a JSON list of crawled articles, runs each through the agent pipeline,
        and returns the total count of processed items.
        """
        if not os.path.exists(filepath):
            logger.warning(f"[BULK INGESTER] Staging file {filepath} not found. Skipping...")
            return 0
            
        with open(filepath, "r", encoding="utf-8") as f:
            articles = json.load(f)
            
        logger.info(f"[BULK INGESTER] Processing {len(articles)} articles from {filepath}...")
        processed_count = 0
        
        for art in articles:
            initial_state = {
                "raw_input": {
                    "title": art.get("title", "Untitled Article"),
                    "content": art.get("content", ""),
                    "source": art.get("source", default_source),
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
            
            try:
                # Trigger the LangGraph Multi-Agent pipeline
                agent_app.invoke(initial_state)
                processed_count += 1
            except Exception as ex:
                logger.error(f"[BULK INGESTER ERROR] Failed to ingest '{art.get('title')}': {ex}")
                
        return processed_count


# ----------------------------------------------------
# Pure REST API Endpoints
# ----------------------------------------------------

@app.get("/search")
def search_news(q: str = Query(..., description="Query string")):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    try:
        return execute_hybrid_search(q)
    except Exception as e:
        logger.error(f"Search endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
def chat_response(payload: ChatRequest):
    """
    Processes chat requests via a POST endpoint. 
    Accepts JSON body: {"message": "ITC stock prices today"}
    """
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")
    try:
        return execute_hybrid_search(message)
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ingest")
def ingest_article(article: ArticleIngest):
    try:
        initial_state = {
            "raw_input": {
                "title": article.title,
                "content": article.content,
                "source": article.source,
                "published_at": article.published_at,
                "url": article.url
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
        result = agent_app.invoke(initial_state)
        return {"status": "Success", "article_id": str(result.get("article_id")), "is_duplicate": result.get("is_duplicate")}
    except Exception as e:
        logger.error(f"Ingestion endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@app.post("/ingest-url")
async def ingest_by_url(payload: UrlIngest):
    url = payload.url
    logger.info(f"[API] Processing URL: {url}")
    
    # 1. Run crawler in a background thread executor using the WebScraper class
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            crawl_data = executor.submit(WebScraper.run_crawler_sync, url).result()
            
    except Exception as e:
         logger.error(f"Scraping failed for URL {url}: {e}")
         raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

    # 2. Save raw scraped article to JSON on disk
    scraped_article_dict = {
        "title": crawl_data["title"],
        "content": crawl_data["markdown"],
        "source": "Web URL Ingest",
        "published_at": "Today",
        "url": url
    }
    
    try:
        WebScraper.save_scraped_data_to_json(scraped_article_dict)
    except Exception as e:
        logger.error(f"Failed writing to disk cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to write to JSON disk cache: {str(e)}")

    # 3. Read back the cached JSON article from disk
    try:
        loaded_article = WebScraper.load_latest_scraped_article()
        logger.info(f"[DISK CACHE] Successfully read back article: '{loaded_article['title']}'")
    except Exception as e:
        logger.error(f"Failed reading from disk cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read from JSON disk cache: {str(e)}")

    # 4. Invoke LangGraph Agents with the loaded raw data
    try:
        initial_state = {
            "raw_input": loaded_article,
            "cleaned_article": None,
            "is_duplicate": False,
            "duplicate_of_id": None,
            "similarity_score": 0.0,
            "entities": [],
            "impacted_stocks": [],
            "article_id": None,
            "errors": []
        }
        
        result_state = agent_app.invoke(initial_state)
        
        if result_state.get("errors"):
             logger.error(f"Agent pipeline errors: {result_state['errors']}")
             raise HTTPException(status_code=500, detail=f"Agent pipeline errors: {result_state['errors']}")
             
        return {
            "status": "Success",
            "title": loaded_article["title"],
            "article_id": str(result_state.get("article_id")),
            "is_duplicate": result_state.get("is_duplicate"),
            "match_score": result_state.get("similarity_score"),
            "entities_extracted": len(result_state.get("entities", []))
        }
        
    except Exception as e:
        logger.error(f"Agent workflow execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Agent workflow execution failed: {str(e)}")

@app.post("/api/ingest")
def trigger_bulk_ingestion():
    try:
        # Use class-based Bulkingester to process staged json caches
        rbi_count = BulkIngester.ingest_from_file("data/raw_rbi.json", "RBI")
        exchange_count = BulkIngester.ingest_from_file("data/raw_exchanges.json", "Exchanges")
        
        return {
            "status": "Success",
            "message": "Bulk files ingested successfully.",
            "details": {
                "rbi_ingested": rbi_count,
                "exchanges_ingested": exchange_count
            }
        }
    except Exception as e:
        logger.error(f"Bulk ingestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)