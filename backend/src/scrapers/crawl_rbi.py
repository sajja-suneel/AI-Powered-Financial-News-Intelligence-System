import asyncio
import os
import json
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode

# Target URLs
RBI_BASE_URL = "https://www.rbi.org.in/Scripts/"
RBI_INDEX_URL = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"
OUTPUT_FILE = "data/mock_dataset.json"

async def scrape_rbi_press_releases(limit: int = 5):
    print("--- STARTING CRAWL4AI SCRAPER: RBI Press Releases ---")
    
    scraped_articles = []
    
    # 1. Start the Crawl4AI Async Crawler
    async with AsyncWebCrawler(verbose=True) as crawler:
        # Step A: Load the main press release listing page
        index_result = await crawler.arun(
            url=RBI_INDEX_URL,
            cache_mode=CacheMode.BYPASS,
            bypass_robots=True
        )
        
        if not index_result.success:
            print(f"Failed to scrape RBI index page: {index_result.error_message}")
            return []
            
        print("Index page fetched successfully. Parsing links...")
        
        # Step B: Parse the links using BeautifulSoup on the rendered HTML
        soup = BeautifulSoup(index_result.html, "html.parser")
        
        # Locate all press release hyperlinks (RBI uses class='link2' for listings)
        link_elements = soup.find_all("a", class_="link2")
        
        if not link_elements:
            print("Warning: No press release links found. Check if the page layout has changed.")
            return []
            
        print(f"Found {len(link_elements)} links on the page. Crawling the top {limit}...")
        
        # Step C: Iterate and crawl each detail page
        for idx, element in enumerate(link_elements[:limit]):
            title = element.get_text(strip=True)
            href = element.get("href", "")
            
            # Resolve relative link URLs
            if not href.startswith("http"):
                detail_url = RBI_BASE_URL + href
            else:
                detail_url = href
                
            print(f"[{idx+1}/{limit}] Fetching details from: {detail_url}")
            
            # Crawl the individual press release content
            detail_result = await crawler.arun(
                url=detail_url,
                cache_mode=CacheMode.BYPASS
            )
            
            if detail_result.success:
                # Crawl4AI automatically gives us clean Markdown (.markdown)
                markdown_content = detail_result.markdown
                
                scraped_articles.append({
                    "title": title,
                    "content": markdown_content,
                    "source": "RBI",
                    "url": detail_url
                })
            else:
                print(f"Failed to crawl detail page {detail_url}: {detail_result.error_message}")
                
    # Step D: Save the raw scraped data to a JSON file
    if scraped_articles:
        # Create data/ folder if it doesn't exist
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(scraped_articles, f, indent=4, ensure_ascii=False)
            
        print(f"\n--- SUCCESS: Saved {len(scraped_articles)} raw articles to {OUTPUT_FILE} ---")
    else:
        print("No articles crawled.")
        
    return scraped_articles

if __name__ == "__main__":
    # Run the crawler logic
    asyncio.run(scrape_rbi_press_releases(limit=5))