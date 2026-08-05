# src/api/routes.py
import os
import json
import concurrent.futures
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from src.agents.query_processor import execute_hybrid_search
from src.graph.workflow import app as agent_app
from src.utils.scraper import WebScraper
from src.utils.logger import get_logger
from src.utils.mongodb_history import MongoChatHistory

logger = get_logger("api.routes")
router = APIRouter()

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
    url: Optional[str] = Field(None, description="A single URL of a financial news page to scrape and ingest")
    urls: Optional[List[str]] = Field(None, description="A list of URLs of financial news pages to scrape and ingest")

class ChatRequest(BaseModel):
    message: str = Field(..., description="The search query or chat message sent by the user")
    session_id: Optional[str] = Field("default", description="The chat session/conversation ID")


# ----------------------------------------------------
# Class-Based Ingestion Helper
# ----------------------------------------------------
class BulkIngester:
    """
    Manages loading raw scraped JSON files from disk and triggering
    the LangGraph agent pipeline to clean, deduplicate, and store the articles.
    """
    @staticmethod
    def ingest_from_file(filepath: str, default_source: str) -> int:
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
                agent_app.invoke(initial_state)
                processed_count += 1
            except Exception as ex:
                logger.error(f"[BULK INGESTER ERROR] Failed to ingest '{art.get('title')}': {ex}")
                
        return processed_count


# ----------------------------------------------------
# API Endpoint Routes
# ----------------------------------------------------

@router.get("/search")
def search_news(q: str = Query(..., description="Query string")):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    try:
        return execute_hybrid_search(q)
    except Exception as e:
        logger.error(f"Search endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def contextualize_query(message: str, history: list) -> str:
    """
    Uses contextualize prompts to reformulate follow-up query using conversation history.
    """
    if not history:
        return message
        
    history_str = ""
    for turn in history:
        history_str += f"User: {turn.get('query')}\nAssistant: {turn.get('explanation')}\n"
        
    from src.utils.prompts import get_contextualize_system_prompt, get_contextualize_user_prompt
    from src.utils.llm import query_groq
    
    sys_prompt = get_contextualize_system_prompt()
    user_prompt = get_contextualize_user_prompt(history_str, message)
    
    try:
        reformulated = query_groq(user_prompt=user_prompt, system_prompt=sys_prompt)
        return reformulated.strip()
    except Exception as e:
        logger.warning(f"Failed to contextualize query: {e}. Using original query.")
        return message

@router.post("/chat")
def chat_response(payload: ChatRequest):
    message = payload.message.strip()
    session_id = payload.session_id.strip() if payload.session_id else "default"
    
    if not message:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")
        
    # 1. Fetch chat history from MongoDB (last 5 turns)
    history = MongoChatHistory.get_history(session_id, limit=5)

    # 2. Contextualize the query
    active_query = contextualize_query(message, history)
    logger.info(f"[CHAT] Session: {session_id} | Original: '{message}' | Active: '{active_query}'")

    # 3. Execute hybrid search
    try:
        search_result = execute_hybrid_search(active_query)
        explanation = search_result.get("explanation", "")
        
        # 4. Save new turn to MongoDB
        MongoChatHistory.save_turn(session_id, message, active_query, explanation)
                
        return {
            "query": message,
            "reformulated_query": active_query if active_query != message else None,
            "explanation": explanation,
            "results": search_result.get("results", [])
        }
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingest")
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

@router.post("/ingest-url")
async def ingest_by_url(payload: UrlIngest):
    urls = []
    if payload.urls:
        urls.extend(payload.urls)
    if payload.url:
        urls.append(payload.url)
        
    if not urls:
        raise HTTPException(status_code=400, detail="Either 'url' or 'urls' must be provided in the request payload.")
        
    logger.info(f"[API] Resolved {len(urls)} target base URLs: {urls}")
    results = []
    
    for url in urls:
        url = url.strip()
        if not url:
            continue
            
        logger.info(f"[API] Processing URL: {url}")
        
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                crawl_data_list = executor.submit(WebScraper.run_multi_crawler_sync, url, 5).result()
        except Exception as e:
            logger.error(f"Scraping failed for URL {url}: {e}")
            results.append({
                "url": url,
                "status": "Failed",
                "error": f"Scraping failed: {str(e)}"
            })
            continue

        if not crawl_data_list:
            results.append({
                "url": url,
                "status": "Failed",
                "error": "No pages crawled or harvested from this URL."
            })
            continue

        logger.info(f"[API] Scraped {len(crawl_data_list)} pages from base URL {url}")

        for page_data in crawl_data_list:
            page_url = page_data.get("url", url)
            
            scraped_article_dict = {
                "title": page_data["title"],
                "content": page_data["markdown"],
                "source": "Web URL Ingest",
                "published_at": "Today",
                "url": page_url
            }
            
            try:
                WebScraper.save_scraped_data_to_json(scraped_article_dict)
            except Exception as e:
                logger.error(f"Failed writing to disk cache for URL {page_url}: {e}")
                results.append({
                    "url": page_url,
                    "status": "Failed",
                    "error": f"Failed to write to JSON disk cache: {str(e)}"
                })
                continue

            try:
                loaded_article = WebScraper.load_latest_scraped_article()
                logger.info(f"[DISK CACHE] Successfully read back article: '{loaded_article['title']}'")
            except Exception as e:
                logger.error(f"Failed reading from disk cache for URL {page_url}: {e}")
                results.append({
                    "url": page_url,
                    "status": "Failed",
                    "error": f"Failed to read from JSON disk cache: {str(e)}"
                })
                continue

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
                    errors = result_state['errors']
                    logger.error(f"Agent pipeline errors for URL {page_url}: {errors}")
                    results.append({
                        "url": page_url,
                        "status": "Failed",
                        "error": f"Agent pipeline errors: {errors}"
                    })
                    continue
                    
                results.append({
                    "url": page_url,
                    "status": "Success",
                    "title": loaded_article["title"],
                    "article_id": str(result_state.get("article_id")),
                    "is_duplicate": result_state.get("is_duplicate"),
                    "match_score": result_state.get("similarity_score"),
                    "entities_extracted": len(result_state.get("entities", []))
                })
                
            except Exception as e:
                logger.error(f"Agent workflow execution failed for URL {page_url}: {e}")
                results.append({
                    "url": page_url,
                    "status": "Failed",
                    "error": f"Agent workflow execution failed: {str(e)}"
                })
            
    return {
        "status": "Success",
        "processed_count": len(results),
        "results": results
    }

@router.post("/api/ingest")
def trigger_bulk_ingestion():
    try:
        rbi_count = BulkIngester.ingest_from_file("data/raw_rbi.json", "RBI")
        bse_count = BulkIngester.ingest_from_file("data/raw_bse.json", "BSE")
        nse_count = BulkIngester.ingest_from_file("data/raw_nse.json", "NSE")
        exchange_count = BulkIngester.ingest_from_file("data/raw_exchanges.json", "Exchanges")
        
        return {
            "status": "Success",
            "message": "Bulk files ingested successfully.",
            "details": {
                "rbi_ingested": rbi_count,
                "bse_ingested": bse_count,
                "nse_ingested": nse_count,
                "exchanges_ingested": exchange_count
            }
        }
    except Exception as e:
        logger.error(f"Bulk ingestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))