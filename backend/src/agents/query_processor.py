# src/agents/query_processor.py
import json
import re
import uuid
from sqlalchemy import text
from config.database import SessionLocal, qdrant_client
from src.utils.embeddings import get_embedding_model
from src.utils.llm import query_groq
from src.utils.prompts import get_query_intent_prompt, get_context_explanation_prompt
from src.utils.stock_api import resolve_ticker, fetch_live_stock_history_table

model = get_embedding_model()
COLLECTION_NAME = "financial_news"

def clean_rbi_boilerplate(text_content: str) -> str:
    """
    Cleans up crawled website boilerplate (headers, footers, navigation links, and images)
    to leave only the core press release content.
    """
    if not text_content:
        return ""
    # Remove Markdown links and image tags
    text_content = re.sub(r'!\[.*?\]\(.*?\)', '', text_content)
    text_content = re.sub(r'\[.*?\]\(.*?\)', '', text_content)
    
    # Remove standard RBI website header navigation lists
    header_keywords = [
        "Skip to main content", "Increase Font Size", "Apply Dark Theme", 
        "Change Language", "Beti Bachao Beti Padhao", "Opportunities@RBI", 
        "Speeches & Media Interactions", "Organisation Structure", "Notifications",
        "Master Directions", "Screen Reader", "Bank Holidays"
    ]
    lines = text_content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        if any(kw in line for kw in header_keywords):
            continue
        cleaned_lines.append(line)
        
    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r'\n+', '\n', cleaned_text).strip()
    return cleaned_text


def execute_hybrid_search(user_query: str):
    print(f"\n[QUERY PROCESSING] Executing hybrid search for: '{user_query}'")
    
    # 1. Parse intent with Groq
    intent_prompt = get_query_intent_prompt(user_query)
    company_filter = None
    sector_filter = None
    theme_query = user_query
    
    try:
        response = query_groq(intent_prompt)
        clean_response = response.strip().replace("```json", "").replace("```", "")
        intent = json.loads(clean_response)
        company_filter = intent.get("company")
        sector_filter = intent.get("sector")
        if intent.get("theme"):
            theme_query = intent.get("theme")
    except Exception as e:
        print(f"Query parsing warning: {e}. Falling back to default search.")

    # 2. Qdrant Vector search
    query_vector = model.encode(theme_query).tolist()
    try:
        vector_res = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=5
        )
        # Parse string IDs to native Python uuid.UUID objects
        semantic_ids = [
            uuid.UUID(r.payload["article_id"]) 
            for r in vector_res.points 
            if "article_id" in r.payload
        ]
    except Exception as e:
        print(f"Qdrant query error: {e}")
        semantic_ids = []

    # 3. Neon DB lookup with Sector-wide Context Expansion
    db = SessionLocal()
    db_results = []
    
    try:
        sql = """
            SELECT DISTINCT a.id, a.title, a.content, a.source, a.published_at
            FROM articles a
            LEFT JOIN article_entities ae ON a.id = ae.article_id
            LEFT JOIN entities e ON ae.entity_id = e.id
            LEFT JOIN stock_impacts si ON a.id = si.article_id
            LEFT JOIN companies c ON si.company_id = c.id
            LEFT JOIN sectors s ON c.sector_id = s.id
            WHERE a.id = ANY(:semantic_ids)
               OR c.name ILIKE :company
               OR s.name ILIKE :sector
               OR a.title ILIKE :query
            ORDER BY a.published_at DESC
        """
        db_res = db.execute(
            text(sql),
            {
                "semantic_ids": semantic_ids,
                "company": f"%{company_filter}%" if company_filter else "EMPTY_FILTER",
                "sector": f"%{sector_filter}%" if sector_filter else "EMPTY_FILTER",
                "query": f"%{user_query}%"
            }
        ).fetchall()
        
        for row in db_res:
            db_results.append({
                "id": str(row[0]),
                "title": row[1],
                "content": clean_rbi_boilerplate(row[2]),
                "source": row[3],
                "published_at": row[4].isoformat() if row[4] else None
            })
            
    except Exception as e:
        print(f"Postgres query error: {e}")
    finally:
        db.close()

    # 4. Live Indian Stock Market API Search
    live_stock_context = ""
    target_ticker = resolve_ticker(user_query)
    
    if target_ticker:
        # Fetch real-time 10-day history table (First tries key, then defaults keyless)
        live_stock_context = fetch_live_stock_history_table(target_ticker, days=10)
        print(f"[QUERY PROCESSING] Pre-appended live stock prices for: {target_ticker}")

    # 5. Formulate final synthesis context (combining news and live stock prices)
    context_str = ""
    if live_stock_context:
        context_str += f"\n--- LIVE MARKET DATA ---\n{live_stock_context}\n"
        
    for idx, art in enumerate(db_results):
        context_str += f"\n--- ARTICLE {idx+1}: {art['title']} ---\nSource: {art['source']}\n{art['content'][:2000]}\n"

    # Send final combined context to Groq to generate the final synthesized response
    ai_prompt = get_context_explanation_prompt(user_query, context_str)
    
    try:
        explanation = query_groq(ai_prompt)
    except Exception as e:
        explanation = f"Error generating explanation: {e}."

    return {
        "query": user_query,
        "explanation": explanation,
        "results": db_results
    }