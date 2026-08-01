# src/scrape_and_ingest_url.py
import sys
from src.utils.scraper import WebScraper
from src.graph.workflow import app as master_graph
from src.agents.query_processor import execute_hybrid_search

class UrlIngestionPipeline:
    """
    A unified CLI orchestrator class to crawl multiple sub-pages of a website concurrently,
    cache them to disk, and pass each through the LangGraph ingestion pipeline.
    """
    
    @staticmethod
    def run(url: str, test_query: str = None, max_pages: int = 5):
        print(f"\n=== STEP 1: Crawling Website and Sub-pages ===")
        print(f"Base Target: {url}")
        
        # 1. Run Multi-Page Crawler via WebScraper (scrapes index + sub-pages in parallel)
        try:
            scraped_pages = WebScraper.run_multi_crawler_sync(url, max_subpages=max_pages)
            print(f"Scrape completed successfully! Collected {len(scraped_pages)} pages.")
        except Exception as e:
            print(f"Crawl failed: {e}")
            return
            
        print(f"\n=== STEP 2: Processing & Ingesting collected pages ===")
        for idx, page in enumerate(scraped_pages):
            print(f"\n[{idx+1}/{len(scraped_pages)}] Processing page: '{page['title']}'")
            print(f"URL: {page['url']}")

            raw_article_data = {
                "title": page["title"],
                "content": page["markdown"],
                "source": "Web Link Multi Scraper",
                "published_at": "Today",
                "url": page["url"]
            }
            
            # 2. Save raw scraped data to JSON on disk cache
            try:
                WebScraper.save_scraped_data_to_json(raw_article_data)
            except Exception as e:
                print(f"Failed to cache scraped article on disk: {e}")
                continue

            # 3. Read back from disk cache (to verify write integrity)
            try:
                loaded_data = WebScraper.load_latest_scraped_article()
                print(f"[DISK CACHE] Successfully loaded: '{loaded_data['title']}'")
            except Exception as e:
                print(f"Failed to read back article from cache: {e}")
                continue

            # 4. Invoke LangGraph Multi-Agent Pipeline for this sub-page
            print(f"[PIPELINE] Invoking LangGraph Multi-Agent Pipeline...")
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
            
            try:
                result_state = master_graph.invoke(initial_state)
                if result_state.get("errors"):
                    print(f"-> Workflow failed for {page['url']}: {result_state['errors']}")
                else:
                    print(f"-> Success! Article ID: {result_state['article_id']} (Duplicate: {result_state['is_duplicate']})")
            except Exception as e:
                print(f"-> Agent workflow execution failed: {e}")

        # 5. Execute optional test search query at the end
        if test_query:
            print(f"\n=== STEP 3: Executing Hybrid Search & AI Synthesis ===")
            try:
                search_result = execute_hybrid_search(test_query)
                print("\n=== AI RESPONSE ===")
                print(search_result["explanation"])
                print("===================")
            except Exception as e:
                print(f"Test query search failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.scrape_and_ingest_url <URL> [OPTIONAL_SEARCH_QUERY]")
        sys.exit(1)
        
    target_url = sys.argv[1]
    query = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Defaults to crawling the base page and its top 5 internal sub-links
    UrlIngestionPipeline.run(target_url, query, max_pages=5)