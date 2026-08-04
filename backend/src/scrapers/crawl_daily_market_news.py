# src/scrapers/crawl_daily_market_news.py
import asyncio
import os
import json
import sys
import feedparser
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode

# Fix Windows ProactorEventLoop subprocess bug for Playwright/Crawl4AI
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Configuration
RBI_BASE_URL = "https://www.rbi.org.in/Scripts/"
RBI_INDEX_URL = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"
BSE_BASE_URL = "https://www.bseindia.com/"
NSE_BASE_URL = "https://www.nseindia.com/"


# Safe RSS feeds to bypass Akamai/Cloudflare blocks
RSS_FEEDS = {
    "Economic Times Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "BSE / NSE Corporate Actions (Moneycontrol Mirror)": "https://www.moneycontrol.com/rss/marketreports.xml",
    "Markets Business Feed": "https://www.moneycontrol.com/rss/business.xml",
    "Livemint Market News": "https://www.livemint.com/rss/markets",
    "Financial Express Market News": "https://news.google.com/rss/search?q=site:financialexpress.com/market+OR+site:financialexpress.com/economy&hl=en-IN&gl=IN&ceid=IN:en",
    "Trade Brains Market News": "https://www.tradebrains.in/feed/",
    "Business Standard Markets": "https://news.google.com/rss/search?q=site:business-standard.com/markets+OR+site:business-standard.com/economy&hl=en-IN&gl=IN&ceid=IN:en"
}

OUTPUT_FILE_RBI = "data/raw_rbi.json"
OUTPUT_FILE_BSE = "data/raw_bse.json"
OUTPUT_FILE_NSE = "data/raw_nse.json"
OUTPUT_FILE_EXCHANGES = "data/raw_exchanges.json"

# ----------------------------------------------------
# Scraper A: RBI Press Releases (Multi-Page Crawling)
# ----------------------------------------------------
async def scrape_rbi_press_releases(limit: int = 10) -> list:
    print("\n--- [RBI SCRAPING] Fetching latest announcements ---")
    scraped_articles = []
    
    custom_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    async with AsyncWebCrawler(verbose=True) as crawler:
        # Fetch listing index
        index_result = await crawler.arun(
            url=RBI_INDEX_URL,
            cache_mode=CacheMode.BYPASS,
            bypass_robots=True,
            extra_headers=custom_headers
        )
        if not index_result.success:
            print(f"Failed to scrape RBI index: {index_result.error_message}")
            return []
            
        soup = BeautifulSoup(index_result.html, "html.parser")
        link_elements = soup.find_all("a", class_="link2")
        
        if not link_elements:
            print("No RBI links found.")
            return []
            
        print(f"Found {len(link_elements)} RBI links. Crawling top {limit} detail pages...")
        
        # Crawl top 10 detail pages
        for idx, element in enumerate(link_elements[:limit]):
            title = element.get_text(strip=True)
            href = element.get("href", "")
            detail_url = href if href.startswith("http") else RBI_BASE_URL + href
            
            print(f"[{idx+1}/{limit}] Fetching RBI detail: {detail_url}")
            detail_result = await crawler.arun(
                url=detail_url,
                cache_mode=CacheMode.BYPASS,
                bypass_robots=True,
                extra_headers=custom_headers
            )
            
            if detail_result.success:
                scraped_articles.append({
                    "title": title,
                    "content": detail_result.markdown,
                    "source": "RBI Press Release",
                    "url": detail_url
                })
            else:
                print(f"Failed to crawl detail page {detail_url}: {detail_result.error_message}")
                
    if scraped_articles:
        os.makedirs(os.path.dirname(OUTPUT_FILE_RBI), exist_ok=True)
        with open(OUTPUT_FILE_RBI, "w", encoding="utf-8") as f:
            json.dump(scraped_articles, f, indent=4, ensure_ascii=False)
        print(f"--> SUCCESS: Saved {len(scraped_articles)} RBI articles to {OUTPUT_FILE_RBI}")
        
    return scraped_articles

# ----------------------------------------------------
# Scraper B: Economic Times, RSS Feeds (Single-Page XML Parsing)
# ----------------------------------------------------
def scrape_rss_exchanges(limit: int = 10) -> list:
    print("\n--- [RSS FEEDS SCRAPING] Fetching Market News Bulletins ---")
    scraped_news = []
    
    for feed_name, feed_url in RSS_FEEDS.items():
        print(f"Parsing Feed: {feed_name}")
        feed = feedparser.parse(feed_url)
        
        if not feed.entries:
            print(f"Warning: Failed to parse feed {feed_name} (no entries found). Skipping...")
            continue
            
        print(f"Found {len(feed.entries)} entries. Collecting top {limit}...")
        
        # Collect top 10 articles per feed
        for entry in feed.entries[:limit]:
            clean_summary = BeautifulSoup(entry.summary, "html.parser").get_text() if "summary" in entry else ""
            
            scraped_news.append({
                "title": entry.title,
                "content": clean_summary,
                "source": feed_name,
                "published_at": entry.get("published", "Today"),
                "url": entry.link
            })
            
    if scraped_news:
        os.makedirs(os.path.dirname(OUTPUT_FILE_EXCHANGES), exist_ok=True)
        with open(OUTPUT_FILE_EXCHANGES, "w", encoding="utf-8") as f:
            json.dump(scraped_news, f, indent=4, ensure_ascii=False)
        print(f"--> SUCCESS: Saved {len(scraped_news)} Exchange bulletins to {OUTPUT_FILE_EXCHANGES}")
        
    return scraped_news


def scrape_bse_announcements(limit: int = 10) -> list:
    print("\n--- [BSE SCRAPING] Fetching latest corporate announcements ---")
    bse_feed_url = "https://news.google.com/rss/search?q=site:bseindia.com+OR+site:moneycontrol.com/company-notices/bse&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(bse_feed_url)
    
    scraped_announcements = []
    if feed.entries:
        print(f"Found {len(feed.entries)} BSE entries. Collecting top {limit}...")
        for entry in feed.entries[:limit]:
            clean_summary = BeautifulSoup(entry.summary, "html.parser").get_text() if "summary" in entry else ""
            scraped_announcements.append({
                "title": entry.title,
                "content": clean_summary,
                "source": "BSE Announcement",
                "published_at": entry.get("published", "Today"),
                "url": entry.link
            })
            
    if scraped_announcements:
        os.makedirs(os.path.dirname(OUTPUT_FILE_BSE), exist_ok=True)
        with open(OUTPUT_FILE_BSE, "w", encoding="utf-8") as f:
            json.dump(scraped_announcements, f, indent=4, ensure_ascii=False)
        print(f"--> SUCCESS: Saved {len(scraped_announcements)} BSE announcements to {OUTPUT_FILE_BSE}")
        
    return scraped_announcements


def scrape_nse_announcements(limit: int = 10) -> list:
    print("\n--- [NSE SCRAPING] Fetching latest corporate announcements ---")
    nse_feed_url = "https://news.google.com/rss/search?q=site:nseindia.com+OR+site:moneycontrol.com/company-notices/nse&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(nse_feed_url)
    
    scraped_announcements = []
    if feed.entries:
        print(f"Found {len(feed.entries)} NSE entries. Collecting top {limit}...")
        for entry in feed.entries[:limit]:
            clean_summary = BeautifulSoup(entry.summary, "html.parser").get_text() if "summary" in entry else ""
            scraped_announcements.append({
                "title": entry.title,
                "content": clean_summary,
                "source": "NSE Announcement",
                "published_at": entry.get("published", "Today"),
                "url": entry.link
            })
            
    if scraped_announcements:
        os.makedirs(os.path.dirname(OUTPUT_FILE_NSE), exist_ok=True)
        with open(OUTPUT_FILE_NSE, "w", encoding="utf-8") as f:
            json.dump(scraped_announcements, f, indent=4, ensure_ascii=False)
        print(f"--> SUCCESS: Saved {len(scraped_announcements)} NSE announcements to {OUTPUT_FILE_NSE}")
        
    return scraped_announcements

# ----------------------------------------------------
# Main Orchestrator Run Loop
# ----------------------------------------------------
async def run_daily_scraping():
    print("====================================================")
    print("STARTING CONSOLIDATED DAILY FINANCIAL SCRAPING CYCLE")
    print("====================================================")
    
    # 1. Scrape RBI (10 detail pages)
    await scrape_rbi_press_releases(limit=10)
    
    # 2. Scrape BSE Announcements (10 announcements)
    scrape_bse_announcements(limit=10)
    
    # 3. Scrape NSE Announcements (10 announcements)
    scrape_nse_announcements(limit=10)
    
    # 4. Scrape all RSS Feeds (10 articles per feed)
    scrape_rss_exchanges(limit=10)
    
    print("\n====================================================")
    print("DAILY SCRAPING COMPLETE. Staging cache files updated.")
    print("====================================================")

if __name__ == "__main__":
    asyncio.run(run_daily_scraping())