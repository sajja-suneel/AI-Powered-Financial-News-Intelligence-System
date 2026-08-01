# src/utils/scraper.py
import sys
import asyncio
import os
import json
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode
from urllib.parse import urljoin, urlparse  # <-- Added for relative link parsing
from src.utils.logger import get_logger

logger = get_logger("utils.scraper")

class WebScraper:
    """
    A class-based utility that handles thread-isolated web scraping using Crawl4AI
    and local disk caching operations. Supports both single-page and multi-page runs.
    """

    @staticmethod
    def run_crawler_sync(url: str) -> dict:
        """
        Spawns a private Proactor event loop in a background thread to scrape a single URL.
        """
        loop = asyncio.new_event_loop()
        try:
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                
            async def do_crawl():
                custom_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9"
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
    def run_multi_crawler_sync(base_url: str, max_subpages: int = 5) -> list:
        """
        Crawls the base page, extracts internal links matching the same domain,
        and concurrently scrapes the top `max_subpages` links using arun_many.
        """
        loop = asyncio.new_event_loop()
        try:
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                
            async def do_multi_crawl():
                custom_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9"
                }
                
                # Step 1: Crawl the index page to harvest sub-links
                logger.info(f"[MULTI-SCRAPER] Harvesting links from index page: {base_url}")
                async with AsyncWebCrawler(verbose=True) as crawler:
                    index_res = await crawler.arun(
                        url=base_url,
                        cache_mode=CacheMode.BYPASS,
                        bypass_robots=True,
                        extra_headers=custom_headers
                    )
                    if not index_res.success:
                        raise Exception(f"Failed to crawl base index: {index_res.error_message}")
                    
                    soup = BeautifulSoup(index_res.html, "html.parser")
                    base_domain = urlparse(base_url).netloc
                    links_to_crawl = []
                    
                    # Resolve relative links and keep only internal domain paths
                    for anchor in soup.find_all("a", href=True):
                        href = anchor["href"]
                        full_url = urljoin(base_url, href)
                        
                        if urlparse(full_url).netloc == base_domain and full_url != base_url:
                            if full_url not in links_to_crawl:
                                links_to_crawl.append(full_url)
                                
                target_urls = links_to_crawl[:max_subpages]
                if not target_urls:
                    logger.info("[MULTI-SCRAPER] No internal sub-links found. Crawling base page only.")
                    target_urls = [base_url]
                else:
                    logger.info(f"[MULTI-SCRAPER] Found {len(links_to_crawl)} sub-links. Crawling top {len(target_urls)} in parallel...")

                # Step 2: Crawl sub-pages concurrently using arun_many
                scraped_pages = []
                async with AsyncWebCrawler(verbose=True) as crawler:
                    results = await crawler.arun_many(
                        urls=target_urls,
                        cache_mode=CacheMode.BYPASS,
                        bypass_robots=True,
                        extra_headers=custom_headers
                    )
                    
                    for url, res in zip(target_urls, results):
                        if res.success:
                            soup_sub = BeautifulSoup(res.html, "html.parser")
                            title_sub = soup_sub.title.string.strip() if soup_sub.title else "Sub Page"
                            scraped_pages.append({
                                "title": title_sub,
                                "markdown": res.markdown,
                                "url": url
                            })
                        else:
                            logger.warning(f"[MULTI-SCRAPER WARNING] Failed to crawl: {url}")
                            
                return scraped_pages
                
            return loop.run_until_complete(do_multi_crawl())
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
        logger.info(f"[DISK CACHE] Saved raw scraped article to: {file_path}")

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