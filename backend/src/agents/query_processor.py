# src/agents/query_processor.py
import json
import re
import uuid
import math
from datetime import datetime
from sqlalchemy import text
from typing import List, Dict
from config.database import SessionLocal, qdrant_client
from src.utils.embeddings import get_embedding_model
from src.utils.logger import get_logger
from src.utils.llm import query_groq
from src.utils.prompts import (
    get_query_intent_system_prompt,
    get_query_intent_user_prompt,
    get_explanation_system_prompt,
    get_explanation_user_prompt
)
from src.utils.stock_api import resolve_ticker_dynamically, fetch_live_stock_history_table

logger = get_logger("agent.query_processor")

class BM25Okapi:
    """
    Lightweight, self-contained BM25 Okapi lexical ranking implementation.
    """
    def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.avgdl = sum(len(doc) for doc in corpus) / self.corpus_size if self.corpus_size > 0 else 0
        self.doc_freqs = []
        self.idf = {}
        self.doc_len = []
        self.nd = {}
        
        for doc in corpus:
            self.doc_len.append(len(doc))
            frequencies = {}
            for word in doc:
                frequencies[word] = frequencies.get(word, 0) + 1
            self.doc_freqs.append(frequencies)
            
            for word in frequencies:
                self.nd[word] = self.nd.get(word, 0) + 1
                
        for word, freq in self.nd.items():
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))

    def get_scores(self, query: List[str]) -> List[float]:
        scores = []
        for index in range(self.corpus_size):
            score = 0.0
            doc_len = self.doc_len[index]
            freqs = self.doc_freqs[index]
            for word in query:
                if word in freqs:
                    freq = freqs[word]
                    idf = self.idf.get(word, 0.0)
                    score += idf * (freq * (self.k1 + 1)) / (freq + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl))
            scores.append(score)
        return scores


def tokenize_text(text_str: str) -> List[str]:
    """
    Cleans and tokenizes text into lowercase word tokens.
    """
    if not text_str:
        return []
    return re.findall(r'\b\w+\b', text_str.lower())


class QueryProcessor:
    """
    Manages the hybrid search execution (vector search on Qdrant + relational queries on Neon)
    and handles temporal-anchored RAG context generation with Groq.
    """
    COLLECTION_NAME = "financial_news"
    
    # Expanded keyword list to trigger live lookup for stock prices, gold, forex, and company profits
    FINANCIAL_KEYWORDS = [
        "price", "rate", "stock", "share", "value", "gold", "usd", "inr", 
        "close", "trade", "chart", "profit", "earning", "revenue", "results", 
        "income", "financial", "nse", "bse", "rbi"
    ]

    @staticmethod
    def _clean_rbi_boilerplate(text_content: str) -> str:
        """
        Removes navigation bars, accessibility menus, and sitemap boilerplate from scraped RBI content.
        """
        if not text_content:
            return ""
        text_content = re.sub(r'!\[.*?\]\(.*?\)', '', text_content)
        text_content = re.sub(r'\[.*?\]\(.*?\)', '', text_content)
        
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

    @staticmethod
    def execute_search(user_query: str) -> dict:
        """
        Runs hybrid semantic + lexical search, structured check fallbacks,
        and stock price endpoints before synthesizing answers.
        """
        logger.info(f"[QUERY PROCESSING] Executing hybrid search for: '{user_query}'")
        
        model = get_embedding_model()
        
        # 1. Fetch separated prompts for intent parsing
        intent_sys = get_query_intent_system_prompt()
        intent_user = get_query_intent_user_prompt(user_query)
        
        company_filter = None
        sector_filter = None
        theme_query = user_query
        
        try:
            # Query Groq using System & User intent prompts
            response = query_groq(user_prompt=intent_user, system_prompt=intent_sys)
            clean_response = response.strip().replace("```json", "").replace("```", "")
            intent = json.loads(clean_response)
            company_filter = intent.get("company")
            sector_filter = intent.get("sector")
            if intent.get("theme"):
                theme_query = intent.get("theme")
        except Exception as e:
            logger.warning(f"Query parsing warning: {e}. Falling back to default search.")

        # Fetch unique database articles to construct the local corpus for BM25
        db = SessionLocal()
        all_articles = []
        try:
            sql = "SELECT id, title, content, source, published_at FROM articles WHERE is_duplicate = FALSE OR is_duplicate IS NULL"
            db_res = db.execute(text(sql)).fetchall()
            for row in db_res:
                all_articles.append({
                    "id": str(row[0]),
                    "title": row[1] or "",
                    "content": row[2] or "",
                    "source": row[3] or "Unknown",
                    "published_at": row[4]
                })
        except Exception as e:
            logger.error(f"Postgres fetch error: {e}")
        finally:
            db.close()

        # 2. Qdrant Semantic search
        semantic_ranks = {}
        if all_articles:
            query_vector = model.encode(theme_query).tolist()
            try:
                vector_res = qdrant_client.query_points(
                    collection_name=QueryProcessor.COLLECTION_NAME,
                    query=query_vector,
                    limit=10
                )
                for rank, point in enumerate(vector_res.points, 1):
                    if "article_id" in point.payload:
                        semantic_ranks[str(point.payload["article_id"])] = rank
            except Exception as e:
                logger.error(f"Qdrant query error: {e}")

        # 3. BM25 Lexical search
        bm25_ranks = {}
        if all_articles:
            try:
                corpus_docs = []
                for art in all_articles:
                    combined_text = f"{art['title']} {art['content']}"
                    corpus_docs.append(tokenize_text(combined_text))
                
                bm25 = BM25Okapi(corpus_docs)
                query_tokens = tokenize_text(theme_query)
                scores = bm25.get_scores(query_tokens)
                
                scored_articles = [(all_articles[idx]["id"], score) for idx, score in enumerate(scores)]
                scored_articles = sorted(scored_articles, key=lambda x: x[1], reverse=True)
                
                rank = 1
                for art_id, score in scored_articles:
                    if score > 0.0:
                        bm25_ranks[art_id] = rank
                        rank += 1
            except Exception as e:
                logger.error(f"BM25 search error: {e}")

        # 4. Metadata Filtering & Alignment
        metadata_ranks = {}
        if all_articles and (company_filter or sector_filter):
            db = SessionLocal()
            try:
                sql = """
                    SELECT DISTINCT a.id
                    FROM articles a
                    LEFT JOIN stock_impacts si ON a.id = si.article_id
                    LEFT JOIN companies c ON si.company_id = c.id
                    LEFT JOIN sectors s ON c.sector_id = s.id
                    WHERE c.name ILIKE :company
                       OR s.name ILIKE :sector
                """
                db_res = db.execute(
                    text(sql),
                    {
                        "company": f"%{company_filter}%" if company_filter else "EMPTY_FILTER",
                        "sector": f"%{sector_filter}%" if sector_filter else "EMPTY_FILTER"
                    }
                ).fetchall()
                for row in db_res:
                    metadata_ranks[str(row[0])] = 1  # Boost metadata matches
            except Exception as e:
                logger.error(f"Postgres metadata query error: {e}")
            finally:
                db.close()

        # 5. Reciprocal Rank Fusion (RRF)
        RRF_K = 60
        rrf_scores = {}
        all_candidate_ids = set(semantic_ranks.keys()).union(set(bm25_ranks.keys())).union(metadata_ranks.keys())
        
        for art_id in all_candidate_ids:
            score = 0.0
            if art_id in semantic_ranks:
                score += 1.0 / (RRF_K + semantic_ranks[art_id])
            if art_id in bm25_ranks:
                score += 1.0 / (RRF_K + bm25_ranks[art_id])
            if art_id in metadata_ranks:
                score += 1.0 / (RRF_K + metadata_ranks[art_id])
            rrf_scores[art_id] = score
            
        sorted_art_ids = sorted(all_candidate_ids, key=lambda x: rrf_scores[x], reverse=True)[:5]

        # Retrieve detailed rows in fused sorting order
        db_results = []
        articles_by_id = {art["id"]: art for art in all_articles}
        for art_id in sorted_art_ids:
            if art_id in articles_by_id:
                art = articles_by_id[art_id]
                db_results.append({
                    "id": art["id"],
                    "title": art["title"],
                    "content": QueryProcessor._clean_rbi_boilerplate(art["content"]),
                    "source": art["source"],
                    "published_at": art["published_at"].isoformat() if hasattr(art["published_at"], "isoformat") else str(art["published_at"]) if art["published_at"] else None
                })

        # 6. Smart Stock Market API Search Check
        live_stock_context = ""
        is_db_empty = len(db_results) == 0
        
        # We now ONLY hit the stock API if Qdrant and Neon returned ZERO articles.
        # This prioritizes the database first.
        if is_db_empty:
            target_ticker = resolve_ticker_dynamically(user_query)
            if target_ticker:
                live_stock_context = fetch_live_stock_history_table(target_ticker, days=10)
                logger.info(f"[QUERY PROCESSING] Database was empty. Pre-appended live stock prices for: {target_ticker}")
        else:
            logger.info("[QUERY PROCESSING] News found in database. Bypassing live stock API lookup.")

        # 7. Formulate final synthesis context
        context_str = ""
        if live_stock_context:
            context_str += f"\n--- LIVE MARKET DATA ---\n{live_stock_context}\n"
            
        for idx, art in enumerate(db_results):
            context_str += f"\n--- ARTICLE {idx+1}: {art['title']} ---\nSource: {art['source']}\n{art['content'][:2000]}\n"

        # Get Live Date/Time for Temporal Anchoring
        current_time_str = datetime.now().strftime("%A, %d-%B-%Y %I:%M %p")

        # 8. Retrieve split System & User prompts for Groq
        system_prompt = get_explanation_system_prompt(current_time_str)
        user_prompt = get_explanation_user_prompt(user_query, context_str)
        
        try:
            explanation = query_groq(user_prompt=user_prompt, system_prompt=system_prompt)
        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            explanation = f"Error generating explanation: {e}."

        return {
            "query": user_query,
            "explanation": explanation,
            "results": db_results
        }

# Module-level alias for backward compatibility
execute_hybrid_search = QueryProcessor.execute_search
