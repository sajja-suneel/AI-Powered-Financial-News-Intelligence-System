@echo off
:: Set directory automatically to the folder where this batch file sits
cd /d "%~dp0"

:: 1. Activate the Python Virtual Environment
call venv\Scripts\activate

echo ==================================================
echo Starting Daily Financial Scrapers...
echo ==================================================
:: 2. Scrape latest RBI, ET, and Moneycontrol BSE/NSE RSS feeds
python -m src.scrapers.crawl_daily_market_news

echo ==================================================
echo Triggering Database Ingestion (Qdrant and Neon)...
echo ==================================================
:: 3. Post data to FastAPI endpoint
curl -X POST "http://127.0.0.1:8000/api/ingest"

echo ==================================================
echo Daily Ingestion Task Triggered!
echo ==================================================
pause 

 