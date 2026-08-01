# src/agents/entity_extractor.py
import json
import re
import spacy
from src.graph.state import AgentState
from src.utils.llm import query_groq
from src.utils.prompts import get_entity_extraction_prompt
from src.utils.logger import get_logger

logger = get_logger("agent.entity_extractor")

class EntityExtractorAgent:
    """
    Analyzes article text to extract financial entities (Companies, Sectors, Regulators)
    using hybrid NLP methods: LLM prompts (via Groq) and a local spaCy NER fallback.
    """
    # Lazy loader for the local spaCy model
    _nlp_instance = None

    @classmethod
    def get_nlp(cls):
        """
        Loads and caches the local spaCy small model on-demand.
        """
        if cls._nlp_instance is None:
            logger.info("[NER] Loading 'en_core_web_sm' spaCy model into memory...")
            cls._nlp_instance = spacy.load("en_core_web_sm")
        return cls._nlp_instance

    @staticmethod
    def _clean_and_parse_json_array(raw_text: str) -> list:
        """
        Cleans markdown code blocks and extracts the outermost JSON array [...]
        """
        text = raw_text.strip().replace("```json", "").replace("```", "")
        
        # Locate the outer brackets to isolate the JSON array
        start_idx = text.find('[')
        end_idx = text.rfind(']')
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError("No JSON array bracket found in response.")
            
        json_str = text[start_idx:end_idx+1]
        return json.loads(json_str)

    @staticmethod
    def extract_entities(state: AgentState) -> AgentState:
        """
        LangGraph Node function that processes clean article text and populates 
        extracted entities into the shared state.
        """
        if state.get("errors") or state.get("is_duplicate"):
            return state
            
        article = state.get("cleaned_article")
        if not article:
            state["errors"].append("Extractor: No cleaned article found in state.")
            return state
            
        logger.info(f"[SUBAGENT] Entity Extractor: Resolving entities for '{article['title']}'...")
        
        # 1. Retrieve the lazy-loaded spaCy model
        nlp = EntityExtractorAgent.get_nlp()
        doc = nlp(article["content"])
        
        # Deduplicate and limit to top 15 hints to prevent context/token bloat
        spacy_hints = list(set([ent.text.strip() for ent in doc.ents if ent.label_ in ["ORG", "MONEY", "LAW"]]))[:15]
        
        try:
            # Truncate content to keep prompt compact and fast
            truncated_content = article["content"][:2000]
            
            # 2. Query Groq LLM
            prompt = get_entity_extraction_prompt(truncated_content, spacy_hints)
            response = query_groq(prompt)
            
            # 3. Clean and parse LLM JSON
            state["entities"] = EntityExtractorAgent._clean_and_parse_json_array(response)
            logger.info(f"--> Extracted {len(state['entities'])} entities via LLM.")
            
        except Exception as e:
            logger.warning(f"[JSON PARSE WARNING]: LLM extraction failed ({e}). Falling back to local spaCy NER.")
            
            # Graceful Fallback: Map local spaCy results instead of crashing
            fallback_entities = []
            for hint in spacy_hints[:10]:  # Limit to top 10 to keep it clean
                category = "Regulator" if hint.lower() in ["rbi", "sebi", "government"] else "Company"
                fallback_entities.append({"name": hint, "category": category})
                
            state["entities"] = fallback_entities
            logger.info(f"--> Populated {len(state['entities'])} entities using local spaCy fallback.")
            
        return state

# ----------------------------------------------------
# Module-level alias to keep other files backward-compatible
# ----------------------------------------------------
extraction_subagent = EntityExtractorAgent.extract_entities