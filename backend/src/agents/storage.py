# src/agents/storage.py
import uuid
from sqlalchemy import text
from src.graph.state import AgentState
from src.utils.embeddings import get_embedding_model
from src.utils.logger import get_logger
from config.database import SessionLocal, qdrant_client
from qdrant_client.http import models

logger = get_logger("agent.storage")

class StorageAgent:
    """
    Finalizes the news ingestion workflow by saving relational metadata to Neon PostgreSQL
    and upserting smart-chunked dense vector embeddings to Qdrant Cloud.
    """
    COLLECTION_NAME = "financial_chatbot_news"

    @staticmethod
    def _chunk_text(text_content: str, chunk_size: int = 800, chunk_overlap: int = 200,
                    table_chunk_size: int = 100, table_chunk_overlap: int = 30) -> list:
        """
        Splits text content into overlapping chunks. Standard text is split using 
        sentence/word boundary alignment. Markdown tables are split horizontally 
        (row-by-row), preserving headers and carrying over overlapping rows.
        """
        if not text_content:
            return []

        # Helper to chunk standard text block
        def chunk_plain_text(text: str) -> list:
            if not text:
                return []
            chunks = []
            start = 0
            text_len = len(text)
            while start < text_len:
                end = start + chunk_size
                if end >= text_len:
                    chunks.append(text[start:].strip())
                    break
                split_idx = text.rfind(".", start, end)
                if split_idx == -1 or split_idx < start + (chunk_size // 2):
                    split_idx = text.rfind(" ", start, end)
                if split_idx != -1:
                    end = split_idx + 1
                chunks.append(text[start:end].strip())
                start = end - chunk_overlap
            return [c for c in chunks if c]

        # Helper to chunk markdown table horizontally (row-by-row)
        def chunk_markdown_table(table_lines: list) -> list:
            if len(table_lines) < 3:
                # If there are not enough lines to form header + separator + rows, treat as plain text
                return chunk_plain_text("\n".join(table_lines))
                
            header_lines = table_lines[:2]
            header_text = "\n".join(header_lines) + "\n"
            data_rows = table_lines[2:]
            
            table_chunks = []
            current_rows = []
            
            for row in data_rows:
                # Calculate proposed chunk text length
                # Format: header_lines + current_rows + row
                proposed_text = header_text + "\n".join(current_rows + [row])
                
                # If the proposed chunk fits within the size, or if it is the first row we are adding, add it
                if len(proposed_text) <= table_chunk_size or not current_rows:
                    current_rows.append(row)
                else:
                    # Finalize current table chunk
                    table_chunks.append(header_text + "\n".join(current_rows))
                    
                    # Compute overlapping rows to carry over to next chunk
                    overlap_rows = []
                    overlap_len = 0
                    for r in reversed(current_rows):
                        row_len = len(r) + 1  # +1 for newline
                        if overlap_len + row_len <= table_chunk_overlap and len(overlap_rows) < len(current_rows) - 1:
                            overlap_rows.insert(0, r)
                            overlap_len += row_len
                        else:
                            break
                            
                    # Fallback: if no rows are overlapped, but we have multiple rows, carry over 1 row to maintain context
                    if not overlap_rows and len(current_rows) > 1:
                        overlap_rows = [current_rows[-1]]
                        
                    current_rows = list(overlap_rows) + [row]
                    
            if current_rows:
                table_chunks.append(header_text + "\n".join(current_rows))
                
            return table_chunks

        # Parse text into blocks of "text" and "table"
        lines = text_content.splitlines()
        blocks = []
        current_block_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            is_table_row = "|" in line
            
            # Check if this represents the start of a valid markdown table
            is_table_start = False
            if is_table_row and i + 1 < len(lines):
                next_line = lines[i + 1]
                # A markdown table divider only contains pipes, dashes, colons, and spaces
                cleaned_next = next_line.replace(" ", "").replace("-", "").replace(":", "").replace("|", "")
                if len(cleaned_next) == 0 and "|" in next_line and "-" in next_line:
                    is_table_start = True
                    
            if is_table_start:
                # Flush the preceding text block
                if current_block_lines:
                    blocks.append(("text", current_block_lines))
                    current_block_lines = []
                
                # Extract the table lines
                table_lines = [line, lines[i + 1]]
                i += 2
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i])
                    i += 1
                blocks.append(("table", table_lines))
                continue
                
            current_block_lines.append(line)
            i += 1
            
        if current_block_lines:
            blocks.append(("text", current_block_lines))
            
        # Process and combine chunks from each block in order
        all_chunks = []
        for block_type, block_lines in blocks:
            if block_type == "table":
                all_chunks.extend(chunk_markdown_table(block_lines))
            else:
                block_text = "\n".join(block_lines)
                all_chunks.extend(chunk_plain_text(block_text))
                
        return all_chunks

    @staticmethod
    def save_to_databases(state: AgentState) -> AgentState:
        """
        LangGraph Node function that writes article details, entities, and impacts to
        PostgreSQL and upserts chunked vectors to Qdrant.
        """
        logger.info("[SUBAGENT] Finalizer: Saving state...")
        
        article = state.get("cleaned_article")
        if not article:
            state["errors"].append("Finalizer: No cleaned article found in state.")
            return state
            
        db = SessionLocal()
        article_id = uuid.uuid4()
        state["article_id"] = article_id
        
        # 1. Neon PostgreSQL Transaction (Relational SQL Data - Full Article)
        try:
            # Save core article fields
            db.execute(
                text("""
                INSERT INTO articles (id, title, content, source, published_at, is_duplicate, duplicate_of_id)
                VALUES (:id, :title, :content, :source, :published_at, :is_duplicate, :duplicate_of_id)
                """),
                {
                    "id": article_id,
                    "title": article["title"],
                    "content": article["content"],
                    "source": article["source"],
                    "published_at": article["published_at"],
                    "is_duplicate": state["is_duplicate"],
                    "duplicate_of_id": state["duplicate_of_id"]
                }
            )
            
            # Save stock impact mapping metadata (Only if unique)
            if not state["is_duplicate"]:
                for impact in state["impacted_stocks"]:
                    db.execute(
                        text("""
                        INSERT INTO stock_impacts (article_id, company_id, confidence_score, impact_type, sentiment, reasoning)
                        SELECT :aid, id, :score, :type, :sentiment, :reasoning FROM companies WHERE ticker = :ticker
                        """),
                        {
                            "aid": article_id,
                            "score": impact["confidence"],
                            "type": impact["type"],
                            "sentiment": impact["sentiment"],
                            "reasoning": impact["reasoning"],
                            "ticker": impact["symbol"]
                        }
                    )
                    
                # Save extracted NLP entities to Postgres (Only if unique)
                for entity in state.get("entities", []):
                    name = entity.get("name", "").strip()
                    category = entity.get("category", "General").strip()
                    if name:
                        # 1. Insert entity (ignoring duplicates)
                        db.execute(
                            text("""
                            INSERT INTO entities (name, category)
                            VALUES (:name, :category)
                            ON CONFLICT (name, category) DO NOTHING
                            """),
                            {"name": name, "category": category}
                        )
                        # 2. Link entity to article in junction table
                        db.execute(
                            text("""
                            INSERT INTO article_entities (article_id, entity_id)
                            VALUES (
                                :aid, 
                                (SELECT id FROM entities WHERE name = :name AND category = :category)
                            )
                            ON CONFLICT DO NOTHING
                            """),
                            {"aid": article_id, "name": name, "category": category}
                        )
                    
            db.commit()
            logger.info("--> Saved to Neon Database successfully.")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Postgres Storage Error: {e}")
            state["errors"].append(f"Storage Postgres: {str(e)}")
            return state
        finally:
            db.close()
            
        # 2. Qdrant Cloud Vector Indexing (Only if unique - Store Smart Chunks)
        if not state["is_duplicate"]:
            try:
                # Retrieve cached singleton embedding model
                model = get_embedding_model()
                
                # Split content into smart text chunks
                chunks = StorageAgent._chunk_text(article["content"], chunk_size=1000, chunk_overlap=200)
                points = []
                
                for idx, chunk in enumerate(chunks):
                    # Inject metadata headers to solve the pronoun/reference context problem
                    metadata_header = f"[Source: {article['source']} | Title: {article['title']}]\n"
                    content_with_metadata = metadata_header + chunk
                    
                    # Generate dense embedding vector locally
                    vector = model.encode(content_with_metadata).tolist()
                    
                    # Generate a deterministic chunk ID based on the main article_id and chunk index
                    chunk_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{article_id}_{idx}"))
                    
                    payload = {
                        "article_id": str(article_id),
                        "chunk_index": idx,
                        "title": article["title"],
                        "content": chunk,  # Store the clean text chunk
                        "source": article["source"],
                        "url": article.get("url", ""),
                        "sectors": [ent["name"] for ent in state["entities"] if ent["category"] == "Sector"],
                        "companies": [ent["name"] for ent in state["entities"] if ent["category"] == "Company"]
                    }
                    
                    points.append(
                        models.PointStruct(
                            id=chunk_uuid,
                            vector=vector,
                            payload=payload
                        )
                    )
                
                # Upsert all text chunks to Qdrant Cloud in a single batch
                qdrant_client.upsert(
                    collection_name=StorageAgent.COLLECTION_NAME,
                    points=points
                )
                logger.info(f"--> Indexed {len(points)} text chunks in Qdrant Cloud successfully.")
                
            except Exception as e:
                logger.error(f"Qdrant Index Error: {e}")
                state["errors"].append(f"Storage Qdrant: {str(e)}")
                
        return state

# ----------------------------------------------------
# Module-level alias to keep other files backward-compatible
# ----------------------------------------------------
finalizer_subagent = StorageAgent.save_to_databases