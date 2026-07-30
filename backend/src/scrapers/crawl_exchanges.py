import os
import json
import feedparser
from typing import List, Dict, Any

# MoneyControl RSS Feeds for Business/Markets
MONEYCONTROL_MARKETS_FEED = "https://www.moneycontrol.com/rss/marketreports.xml"
MONEYCONTROL_BUSINESS_FEED = "https://www.moneycontrol.com/rss/business.xml"
OUTPUT_FILE = "data/raw_exchanges.json"

def scrape_financial_rss(limit: int = 10) -> List[Dict[str, Any]]:
    print("--- STARTING RSS SCRAPER: MoneyControl Feeds ---")
    
    scraped_news = []
    
    # We will fetch articles from both feeds
    feeds = [
        {"url": MONEYCONTROL_MARKETS_FEED, "source": "MoneyControl Markets"},
        {"url": MONEYCONTROL_BUSINESS_FEED, "source": "MoneyControl Business"}
    ]
    
    for feed_info in feeds:
        print(f"Parsing feed: {feed_info['url']}")
        
        # Read the RSS feed
        feed = feedparser.parse(feed_info["url"])
        
        # Check if the feed loaded successfully
        if feed.bozo:
            print(f"Warning: Failed to parse feed {feed_info['url']}. Skipping...")
            continue
            
        print(f"Found {len(feed.entries)} entries in feed.")
        
        for entry in feed.entries[:limit]:
            # Convert HTML text to clean plain text
            from bs4 import BeautifulSoup
            clean_summary = BeautifulSoup(entry.summary, "html.parser").get_text() if "summary" in entry else ""
            
            scraped_news.append({
                "title": entry.title,
                "content": clean_summary,
                "source": feed_info["source"],
                "published_at": entry.get("published", "Today"),
                "url": entry.link
            })
            
    # Save the consolidated news list locally
    if scraped_news:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(scraped_news, f, indent=4, ensure_ascii=False)
        print(f"\n--- SUCCESS: Saved {len(scraped_news)} articles to {OUTPUT_FILE} ---")
    else:
        print("No articles collected.")
        
    return scraped_news

if __name__ == "__main__":
    scrape_financial_rss(limit=5)