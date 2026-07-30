# src/scrape_and_ingest_url.py
import sys
import asyncio

# Fix Windows ProactorEventLoop subprocess bug for Playwright/Crawl4AI
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import os
import json
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode
from src.graph.workflow import app as master_graph
from src.agents.query_processor import execute_hybrid_search

JSON_DISK_CACHE = "data/raw_crawled_urls.json"

def cache_scraped_article_on_disk(article_data: dict):
    """Saves raw scraped contents in JSON format to disk"""
    articles = []
    if os.path.exists(JSON_DISK_CACHE):
        try:
            with open(JSON_DISK_CACHE, "r", encoding="utf-8") as f:
                articles = json.load(f)
        except Exception:
            articles = []
    
    articles.append(article_data)
    os.makedirs(os.path.dirname(JSON_DISK_CACHE), exist_ok=True)
    with open(JSON_DISK_CACHE, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=4, ensure_ascii=False)
    print(f"[DISK CACHE] Saved raw scraped article to {JSON_DISK_CACHE}")

def read_scraped_article_from_disk() -> dict:
    """Reads back the last article logged in the local JSON cache"""
    if not os.path.exists(JSON_DISK_CACHE):
        raise FileNotFoundError("Cache file does not exist.")
    with open(JSON_DISK_CACHE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    return articles[-1]

async def scrape_and_ingest(url: str, test_query: str = None):
    print(f"\n=== STEP 1: Crawling URL using Crawl4AI ===")
    print(f"Target: {url}")
    
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
            print(f"Crawl failed: {result.error_message}")
            return
            
        soup = BeautifulSoup(result.html, "html.parser")
        title = soup.title.string.strip() if soup.title else "Scraped Financial News"
        raw_markdown = result.markdown
        print(f"Scrape successful! Title: '{title}'")

    # Save to JSON format on disk first
    raw_article_data = {
        "title": title,
        "content": raw_markdown,
        "source": "Web Link CLI Scraper",
        "published_at": "Today",
        "url": url
    }
    cache_scraped_article_on_disk(raw_article_data)

    # Read back from JSON disk cache
    print(f"\n=== STEP 2: Loading raw data from disk ===")
    loaded_data = read_scraped_article_from_disk()
    print(f"[DISK CACHE] Successfully read back: '{loaded_data['title']}'")

    # Connect to the Ingestion Agent inside the LangGraph state graph
    print(f"\n=== STEP 3: Invoking LangGraph Multi-Agent Pipeline ===")
    initial_state = {
        "raw_input": loaded_data,
        "cleaned_article": None,
        "is_duplicate": False,
        "duplicate_of_id": None,
        "similarity_score": 0.0,
        "entities": [],
        "impacted_stocks": [],
        "article_id": None,
        "errors": []
    }
    
    result_state = master_graph.invoke(initial_state)
    
    if result_state.get("errors"):
        print(f"Workflow failed: {result_state['errors']}")
        return
        
    print(f"Workflow success! Article ID: {result_state['article_id']} (Duplicate: {result_state['is_duplicate']})")

    # Optional query execution
    if test_query:
        print(f"\n=== STEP 4: Executing Hybrid Search & AI Synthesis ===")
        search_result = execute_hybrid_search(test_query)
        print("\n=== AI RESPONSE ===")
        print(search_result["explanation"])
        print("===================")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.scrape_and_ingest_url <URL> [OPTIONAL_SEARCH_QUERY]")
        sys.exit(1)
        
    target_url = sys.argv[1]
    query = sys.argv[2] if len(sys.argv) > 2 else None
    
    asyncio.run(scrape_and_ingest(target_url, query))