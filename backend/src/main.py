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
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode

from src.agents.query_processor import execute_hybrid_search
from src.agents.ingestion import ingest_raw_news_file
from src.graph.workflow import app as agent_app

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

# ----------------------------------------------------
# Thread-Isolated Scraper Wrapper (Bypasses Uvicorn Event Loop limits)
# ----------------------------------------------------
def run_crawler_sync(url: str) -> dict:
    """
    Spawns a private Proactor event loop in a background thread to scrape the URL.
    This prevents Uvicorn's main thread loop policy from crashing Playwright.
    """
    loop = asyncio.new_event_loop()
    try:
        # Enforce Proactor loop policy for this specific background thread
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
        async def do_crawl():
            custom_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            async with AsyncWebCrawler(verbose=True) as crawler:
                result = await crawler.arun(
                    url=url,
                    cache_mode=CacheMode.BYPASS,
                    bypass_robots=True,
                    extra_headers=custom_headers
                )
                if not result.success:
                    raise Exception(result.error_message)
                
                soup = BeautifulSoup(result.html, "html.parser")
                title = soup.title.string.strip() if soup.title else "Scraped Document"
                
                return {
                    "title": title,
                    "markdown": result.markdown
                }
                
        return loop.run_until_complete(do_crawl())
    finally:
        loop.close()

# ----------------------------------------------------
# Disk Caching Utilities
# ----------------------------------------------------
def save_scraped_data_to_json(article_data: dict, file_path: str = "data/raw_crawled_urls.json"):
    articles = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                articles = json.load(f)
        except Exception:
            articles = []
            
    articles.append(article_data)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=4, ensure_ascii=False)
    print(f"[DISK CACHE] Saved raw scraped article to: {file_path}")

def load_latest_scraped_article(file_path: str = "data/raw_crawled_urls.json") -> dict:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Staging file {file_path} not found.")
    with open(file_path, "r", encoding="utf-8") as f:
        articles = json.load(f)
    if not articles:
        raise ValueError(f"No records found in {file_path}")
    return articles[-1]

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
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@app.post("/ingest-url")
async def ingest_by_url(payload: UrlIngest):
    url = payload.url
    print(f"\n[API] Processing URL: {url}")
    
    # 1. Run crawler in a background thread executor
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            crawl_data = executor.submit(run_crawler_sync, url).result()
            
    except Exception as e:
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
        save_scraped_data_to_json(scraped_article_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write to JSON disk cache: {str(e)}")

    # 3. Read back the cached JSON article from disk
    try:
        loaded_article = load_latest_scraped_article()
        print(f"[DISK CACHE] Successfully read back article: '{loaded_article['title']}'")
    except Exception as e:
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
        raise HTTPException(status_code=500, detail=f"Agent workflow execution failed: {str(e)}")

@app.post("/api/ingest")
def trigger_bulk_ingestion():
    try:
        if os.path.exists("data/raw_rbi.json"):
            ingest_raw_news_file("data/raw_rbi.json", "RBI")
        if os.path.exists("data/raw_exchanges.json"):
            ingest_raw_news_file("data/raw_exchanges.json", "Exchanges")
        return {"status": "Success", "message": "Bulk files ingested successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)