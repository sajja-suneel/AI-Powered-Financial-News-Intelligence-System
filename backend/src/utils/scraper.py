# src/utils/scraper.py
import sys
import asyncio
import os
import json
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode

class WebScraper:
    """
    A class-based utility that handles thread-isolated web scraping using Crawl4AI
    and local disk caching operations.
    """

    @staticmethod
    def run_crawler_sync(url: str) -> dict:
        """
        Spawns a private Proactor event loop in a background thread to scrape the URL.
        Bypasses Uvicorn's main thread loop policy to prevent Playwright crashes on Windows.
        """
        loop = asyncio.new_event_loop()
        try:
            # Enforce Proactor loop policy for this specific background thread on Windows
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                
            async def do_crawl():
                # Standard browser request headers to blend in as a real Google Chrome browser
                custom_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
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

    @staticmethod
    def save_scraped_data_to_json(article_data: dict, file_path: str = "data/raw_crawled_urls.json"):
        """
        Saves crawled article dictionary into a local JSON list cache.
        """
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

    @staticmethod
    def load_latest_scraped_article(file_path: str = "data/raw_crawled_urls.json") -> dict:
        """
        Loads the latest crawled article from the local JSON list cache.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Staging file {file_path} not found.")
        with open(file_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
        if not articles:
            raise ValueError(f"No records found in {file_path}")
        return articles[-1]