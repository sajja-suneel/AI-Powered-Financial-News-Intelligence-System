# src/utils/stock_api.py
import os
import requests
import yfinance as ticker_engine
import pandas as pd
from typing import Optional
from dotenv import load_dotenv
from src.utils.llm import query_groq

load_dotenv()

# Load API credentials from .env
API_KEY = os.getenv("INDIAN_STOCK_API_KEY")
API_HOST = os.getenv("INDIAN_STOCK_API_HOST", "indian-stock-exchange-api2.p.rapidapi.com")

def resolve_ticker_dynamically(query: str) -> Optional[str]:
    """
    Uses Llama 3.1 8B as an intelligent 'Tool Caller' to dynamically identify
    the correct NSE/BSE ticker symbol from the user query.
    Takes less than 0.5 seconds on Groq.
    """
    normalized_query = query.lower()
    if "gold" in normalized_query:
        return "GOLDBEES.NS"
        
    resolver_prompt = f"""
    Identify the target Indian stock market ticker symbol (NSE format, ending with .NS or BSE format ending with .BO) 
    for the company or stock mentioned in the user query.
    
    User Query: "{query}"
    
    Rules:
    1. Return ONLY the ticker symbol (e.g., "ITC.NS", "SBIN.NS", "TCS.NS", "TATAMOTORS.NS", "GOLDBEES.NS","HDFC.NS", "BSE.NS",NSE.NS,RBI.NS,TIME OF INDIA.NS,INDIA.NS,KALYANJEWEL.NS).
    2. If no specific company, stock, or index is mentioned, return "NONE".
    3. Do not include any explanations, punctuation, or extra text.
    """
    
    try:
        response = query_groq(resolver_prompt)
        ticker = response.strip().upper().replace('"', '').replace("'", "")
        
        if ticker == "NONE" or len(ticker) > 15:
            return None
            
        print(f"[TICKER RESOLVER] Dynamically resolved query to ticker: {ticker}")
        return ticker
    except Exception as e:
        print(f"[TICKER RESOLVER WARNING] AI resolution failed: {e}. Falling back to default.")
        return None


def fetch_from_third_party_api(ticker: str, days: int = 10) -> Optional[str]:
    if not API_KEY:
        return None
        
    clean_symbol = ticker.split(".")[0]
    
    host = API_HOST.strip()
    if host.startswith("http://"):
        host = host[7:]
    elif host.startswith("https://"):
        host = host[8:]
    host = host.strip("/")
    
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
    third_party_table = fetch_from_third_party_api(ticker, days)
    if third_party_table:
        return third_party_table
        
    try:
        print(f"[STOCK API FALLBACK] Fetching via Yahoo Finance for: {ticker}")
        stock = ticker_engine.Ticker(ticker)
        hist = stock.history(period="1mo")
        
        if hist.empty:
            return f"No stock data could be found for ticker {ticker}."
            
        last_n = hist.tail(days).copy()
        last_n["Daily Change %"] = last_n["Close"].pct_change() * 100
        last_n = last_n.sort_index(ascending=False)
        
        is_gold = (ticker == "GOLDBEES.NS")
        
        markdown_table = f"### 📊 Live Price History ({'Physical Gold [10 grams]' if is_gold else ticker}) [Yahoo Fallback]\n"
        markdown_table += "| Date | Price (₹) | Daily Change |\n"
        markdown_table += "| :--- | :--- | :--- |\n"
        
        for date_timestamp, row in last_n.iterrows():
            date_str = date_timestamp.strftime("%d-%b-%Y")
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
        print(f"[STOCK API ERROR] Fallback failed for {ticker}: {e}")
        return f"Stock price lookup service for {ticker} is currently offline."