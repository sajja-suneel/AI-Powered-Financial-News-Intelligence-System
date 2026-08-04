# src/utils/stock_api.py
import os
import re
import requests
import yfinance as ticker_engine
import pandas as pd
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from src.utils.llm import query_groq
from src.utils.logger import get_logger

logger = get_logger("utils.stock_api")

load_dotenv()

class StockMarketEngine:
    """
    Handles stock, commodity, and currency exchange ticker resolution
    and fetches real-time market data from external API endpoints.
    """
    API_KEY = os.getenv("INDIAN_STOCK_API_KEY")
    API_HOST = os.getenv("INDIAN_STOCK_API_HOST", "indian-stock-exchange-api2.p.rapidapi.com")

    @staticmethod
    def resolve_ticker(query: str) -> Optional[str]:
        """
        Uses Llama 3.1 8B to dynamically identify the target stock market ticker symbol.
        """
        normalized_query = query.lower()
        
        # 1. Fast bypasses for currency, gold, and common stocks
        if "usd to inr" in normalized_query or "usdinr" in normalized_query:
            return "USDINR=X"
        if "gold" in normalized_query:
            return "GOLDBEES.NS"
        if "reliance" in normalized_query:
            return "RELIANCE.NS"
        if "sbi" in normalized_query:
            return "SBIN.NS"
        if "tata" in normalized_query:
            return "TATAMOTORS.NS"
        if "nse" in normalized_query or "bse" in normalized_query:
            # Extract potential ticker from query
            match = re.search(r'\b([A-Z]{1,5})\b', query)
            if match:
                return f"{match.group(1).upper()}.NS"
            if "nifty" in normalized_query:
                return "NIFTY50.NS"
            if "sensex" in normalized_query:
                return "SENSEX.BO"
            if "netflix" in normalized_query:
                return "NFLX"
            if "financial" in normalized_query and "news" in normalized_query:
                return None  # No specific ticker for general financial news
            if "economy" in normalized_query and "india" in normalized_query:
                return None  # No specific ticker for general economic news
            if "rbi" in normalized_query or "reserve bank" in normalized_query:
                return None  # No specific ticker for RBI or Reserve Bank queries
            if "silver" in normalized_query:
                return "SILVER=X"
        # 2. Fast bypass for regulatory bodies (they don't have public stocks)
        if "rbi" in normalized_query or "reserve bank" in normalized_query or "sebi" in normalized_query:
            return None
            
        resolver_prompt = f"""
        Identify the target stock market ticker symbol (NSE format ending in .NS, BSE format ending in .BO, or Currency/Forex format ending in =X)
        for the target mentioned in the query.
        
        User Query: "{query}"
        
        Rules:
        1. Return ONLY the ticker symbol. Examples:
           - "ITC stock price": ITC.NS
           - "USD to INR exchange rate": USDINR=X
           - "EUR to INR": EURINR=X
        2. If the query is about a central bank, regulatory body (like RBI, SEBI, SEC), or policy announcement, return "NONE".
        3. If no specific company, currency pair, or index is mentioned, return "NONE".
        4. Do not include any explanations, punctuation, or extra text.
        """
        
        try:
            response = query_groq(resolver_prompt)
            ticker = response.strip().upper().replace('"', '').replace("'", "")
            
            if ticker == "NONE" or len(ticker) > 15:
                return None
                
            logger.info(f"[TICKER RESOLVER] Dynamically resolved query to ticker: {ticker}")
            return ticker
        except Exception as e:
            logger.warning(f"[TICKER RESOLVER WARNING] AI resolution failed: {e}. Falling back to default.")
            return None

    @staticmethod
    def fetch_from_third_party(ticker: str, days: int = 10) -> Optional[str]:
        """
        Fetches stock data using RapidAPI for standard Indian equities.
        Bypasses calls for Gold (GOLDBEES) and Forex (=X) assets.
        """
        if not StockMarketEngine.API_KEY:
            return None
            
        # RapidAPI only supports standard Indian equities. Skip for Gold or Forex.
        if "GOLDBEES" in ticker or "=X" in ticker:
            return None
            
        clean_symbol = ticker.split(".")[0]
        
        host = StockMarketEngine.API_HOST.strip()
        if host.startswith("http://"):
            host = host[7:]
        elif host.startswith("https://"):
            host = host[8:]
        host = host.strip("/")
        
        url = f"https://{host}/stock/history"
        querystring = {"symbol": clean_symbol, "period": "10d"}
        headers = {
            "X-RapidAPI-Key": StockMarketEngine.API_KEY,
            "X-RapidAPI-Host": host
        }
        
        try:
            logger.info(f"[STOCK API] Fetching via Third-Party Key for symbol: {clean_symbol}")
            response = requests.get(url, headers=headers, params=querystring, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                markdown_table = f"### 📊 Live Stock Price History ({clean_symbol}) [Third-Party API]\n"
                markdown_table += "| Date | Closing Price (₹) | Daily Change |\n"
                markdown_table += "| :--- | :--- | :--- |\n"
                
                for item in data[:days]:
                    date_str = item.get("date", "-")
                    close_price = f"{item.get('close', 0.0):.2f}"
                    change_val = item.get("change", "-")
                    markdown_table += f"| {date_str} | {close_price} | {change_val} |\n"
                    
                return markdown_table
        except Exception as e:
            logger.warning(f"[STOCK API WARNING] Third-party request failed ({e}). Trying fallback...")
            
        return None

    @staticmethod
    def fetch_live_history_table(ticker: str, days: int = 10) -> str:
        """
        Fetches stock history, falling back to Yahoo Finance query1 JSON endpoint.
        """
        third_party_table = StockMarketEngine.fetch_from_third_party(ticker, days)
        if third_party_table:
            return third_party_table
            
        try:
            logger.info(f"[STOCK API FALLBACK] Fetching via Yahoo query1 JSON for: {ticker}")
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d"
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            
            if response.status_code != 200:
                return f"No stock data could be found for ticker {ticker}."
                
            data = response.json()
            result = data.get("chart", {}).get("result", [None])[0]
            if not result:
                return f"No stock data could be found for ticker {ticker}."
                
            timestamps = result.get("timestamp", [])
            indicators = result.get("indicators", {}).get("quote", [{}])[0]
            closes = indicators.get("close", [])
            
            # Align timestamps and close prices, filtering out None values
            history = []
            for t, c in zip(timestamps, closes):
                if t is not None and c is not None:
                    history.append((datetime.fromtimestamp(t), c))
                    
            if not history:
                return f"No stock data could be found for ticker {ticker}."
                
            # Filter to requested number of days
            history = history[-days:]
            
            # Compute daily changes in reverse order
            table_rows = []
            for i in range(len(history) - 1, -1, -1):
                date_dt, close_val = history[i]
                date_str = date_dt.strftime("%d-%b-%Y")
                
                # Percent change from previous day
                if i > 0:
                    prev_close = history[i - 1][1]
                    change_pct = ((close_val - prev_close) / prev_close) * 100
                    if change_pct >= 0:
                        change_str = f"+{change_pct:.2f}%"
                    else:
                        change_str = f"{change_pct:.2f}%"
                else:
                    change_str = "-"
                    
                table_rows.append((date_str, close_val, change_str))
                
            is_gold = (ticker == "GOLDBEES.NS")
            is_forex = ("=X" in ticker)
            
            markdown_table = f"### 📊 Live Price History ({'Physical Gold [10 grams]' if is_gold else ticker}) [Yahoo Fallback]\n"
            markdown_table += f"| Date | {'Exchange Rate (INR)' if is_forex else 'Price (₹)'} | Daily Change |\n"
            markdown_table += "| :--- | :--- | :--- |\n"
            
            for date_str, price, change_str in table_rows:
                display_price = price * 1000 if is_gold else price
                price_str = f"{display_price:.4f}" if is_forex else f"{display_price:.2f}"
                markdown_table += f"| {date_str} | {price_str} | {change_str} |\n"
                
            return markdown_table
            
        except Exception as e:
            logger.error(f"[STOCK API ERROR] Fallback failed for {ticker}: {e}")
            return f"Stock price lookup service for {ticker} is currently offline."

# ----------------------------------------------------
# Module-level aliases to keep other files backward-compatible
# ----------------------------------------------------
resolve_ticker_dynamically = StockMarketEngine.resolve_ticker
fetch_from_third_party_api = StockMarketEngine.fetch_from_third_party
fetch_live_stock_history_table = StockMarketEngine.fetch_live_history_table
