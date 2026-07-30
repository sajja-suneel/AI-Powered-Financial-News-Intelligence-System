# src/utils/stock_api.py
import os
import requests
import yfinance as ticker_engine
import pandas as pd
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Load API credentials from .env
API_KEY = os.getenv("INDIAN_STOCK_API_KEY")
API_HOST = os.getenv("INDIAN_STOCK_API_HOST", "indian-stock-exchange-api2.p.rapidapi.com")

# Mapping of common Indian company names/queries to NSE Tickers
TICKER_MAPPING = {
    "tcs": "TCS.NS",
    "tata consultancy services": "TCS.NS",
    "sbi": "SBIN.NS",
    "state bank of india": "SBIN.NS",
    "hdfc": "HDFCBANK.NS",
    "hdfc bank": "HDFCBANK.NS",
    "reliance": "RELIANCE.NS",
    "infy": "INFY.NS",
    "infosys": "INFY.NS",
    "icici": "ICICIBANK.NS",
    "icici bank": "ICICIBANK.NS",
    
    # Gold BeES tracks 1/100th of a gram of gold. We can multiply it in query results.
    "gold": "GOLDBEES.NS",
    "HEROMOTOCO": "HEROMOTOCO.NS",
    "BSE": "BSE.NS",
    "NSE": "NSE.NS",
    "RBI": "RBI.NS",
    "FINANCE INDIA": "FINANCEINDIA.NS"
    
}

def resolve_ticker(query: str) -> Optional[str]:
    normalized_query = query.lower()
    for name, ticker in TICKER_MAPPING.items():
        if name in normalized_query:
            return ticker
    return None


def fetch_from_third_party_api(ticker: str, days: int = 10) -> Optional[str]:
    """
    Attempts to fetch stock history using the user's third-party API Key.
    """
    if not API_KEY:
        print("[STOCK API] Third-party API Key is missing. Skipping to fallback.")
        return None
        
    # Clean ticker for third party (e.g. TCS.NS -> TCS)
    clean_symbol = ticker.split(".")[0]
    
    # ─── SANITIZE HOSTNAME ───
    # Strips any accidental 'http://', 'https://', and trailing '/' from .env
    host = API_HOST.strip()
    if host.startswith("http://"):
        host = host[7:]
    elif host.startswith("https://"):
        host = host[8:]
    host = host.strip("/")
    
    # Construct clean URL
    url = f"https://{host}/stock/history"
    querystring = {"symbol": clean_symbol, "period": "10d"}
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": host
    }
    
    try:
        print(f"[STOCK API] Fetching via Third-Party Key for symbol: {clean_symbol}")
        response = requests.get(url, headers=headers, params=querystring, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            # Standard formatting loop for API response array
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
        print(f"[STOCK API WARNING] Third-party request failed ({e}). Trying fallback...")
        
    return None


def fetch_live_stock_history_table(ticker: str, days: int = 10) -> str:
    """
    Fetches stock history. First tries the third-party API key,
    and falls back to Yahoo Finance if key is missing or fails.
    """
    # 1. Try Third-Party API Key first
    third_party_table = fetch_from_third_party_api(ticker, days)
    if third_party_table:
        return third_party_table
        
    # 2. Fallback to Yahoo Finance (Keyless)
    try:
        print(f"[STOCK API FALLBACK] Fetching via Yahoo Finance for: {ticker}")
        stock = ticker_engine.Ticker(ticker)
        hist = stock.history(period="1mo")
        
        if hist.empty:
            return "No stock data could be found for this ticker."
            
        last_n = hist.tail(days).copy()
        last_n["Daily Change %"] = last_n["Close"].pct_change() * 100
        last_n = last_n.sort_index(ascending=False)
        
        # Determine if we are tracking Gold (ETF Gold BeES tracks ~1/100th of 1 gram of gold)
        # So we can present the gold price cleanly (multiply GOLDBEES price by 1000 for 10gm rate)
        is_gold = (ticker == "GOLDBEES.NS")
        
        markdown_table = f"### 📊 Live Price History ({'Physical Gold [10 grams]' if is_gold else ticker}) [Yahoo Fallback]\n"
        markdown_table += "| Date | Price (₹) | Daily Change |\n"
        markdown_table += "| :--- | :--- | :--- |\n"
        
        for date_timestamp, row in last_n.iterrows():
            date_str = date_timestamp.strftime("%d-%b-%Y")
            
            # If GOLDBEES (ETF), 1 unit is approx 1/100th of a gram.
            # To get the price of 10 grams, we multiply the closing price of GOLDBEES unit by 1000
            price = row['Close'] * 1000 if is_gold else row['Close']
            price_str = f"{price:.2f}"
            
            change_val = row["Daily Change %"]
            if pd.isna(change_val):
                change_str = "-"
            elif change_val >= 0:
                change_str = f"+{change_val:.2f}%"
            else:
                change_str = f"{change_val:.2f}%"
                
            markdown_table += f"| {date_str} | {price_str} | {change_str} |\n"
            
        return markdown_table
        
    except Exception as e:
        print(f"[STOCK API ERROR] Fallback failed: {e}")
        return "Stock price lookup service is currently offline."