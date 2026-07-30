# src/agents/entity_extractor.py
import json
import re
import spacy
from src.graph.state import AgentState
from src.utils.llm import query_groq
from src.utils.prompts import get_entity_extraction_prompt

nlp = spacy.load("en_core_web_sm")

def clean_and_parse_json_array(raw_text: str) -> list:
    """
    Cleans markdown code blocks and extracts the outermost JSON array [...]
    """
    # Remove markdown code blocks if present
    text = raw_text.strip().replace("```json", "").replace("```", "")
    
    # Locate the outer brackets to isolate the JSON array
    start_idx = text.find('[')
    end_idx = text.rfind(']')
    
    if start_idx == -1 or end_idx == -1:
        raise ValueError("No JSON array bracket found in response.")
        
    json_str = text[start_idx:end_idx+1]
    return json.loads(json_str)


def extraction_subagent(state: AgentState) -> AgentState:
    if state.get("errors") or state.get("is_duplicate"):
        return state
        
    article = state.get("cleaned_article")
    if not article:
        state["errors"].append("Extractor: No cleaned article found in state.")
        return state
        
    print(f"\n[SUBAGENT] Entity Extractor: Resolving entities for '{article['title']}'...")
    
    # Pre-calculate local spaCy entities as hints and fallback
        # Pre-calculate local spaCy entities
        
    doc = nlp(article["content"])
    # ─── OPTIMIZATION: Deduplicate and limit to top 15 hints ───
    spacy_hints = list(set([ent.text.strip() for ent in doc.ents if ent.label_ in ["ORG", "MONEY", "LAW"]]))[:15]
    
    try:
        # ─── OPTIMIZATION: Reduce content character limit to 2000 ───
        truncated_content = article["content"][:2000]
        
        # 2. Query Groq LLM
        prompt = get_entity_extraction_prompt(truncated_content, spacy_hints)
        response = query_groq(prompt)
        
        # 3. Clean and parse LLM JSON
        state["entities"] = clean_and_parse_json_array(response)
        print(f"--> Extracted {len(state['entities'])} entities via LLM.")
        
    except Exception as e:
        print(f"[JSON PARSE WARNING]: LLM extraction failed ({e}). Falling back to local spaCy NER.")
        
        # ─── GRACEFUL FALLBACK: Map local spaCy results instead of crashing ───
        fallback_entities = []
        for hint in spacy_hints[:10]:  # Limit to top 10 to keep it clean
            category = "Regulator" if hint.lower() in ["rbi", "sebi", "government"] else "Company"
            fallback_entities.append({"name": hint, "category": category})
            
        state["entities"] = fallback_entities
        print(f"--> Populated {len(state['entities'])} entities using local spaCy fallback.")
        
    return state