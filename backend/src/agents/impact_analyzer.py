# src/agents/impact_analyzer.py
import json
import re
from src.graph.state import AgentState
from src.utils.llm import query_groq
from src.utils.prompts import get_stock_impact_prompt

def clean_and_parse_json_array(raw_text: str) -> list:
    text = raw_text.strip().replace("```json", "").replace("```", "")
    start_idx = text.find('[')
    end_idx = text.rfind(']')
    if start_idx == -1 or end_idx == -1:
        raise ValueError("No JSON array found in response.")
    return json.loads(text[start_idx:end_idx+1])

def impact_subagent(state: AgentState) -> AgentState:
    if state.get("errors") or state.get("is_duplicate"):
        return state
        
    article = state.get("cleaned_article")
    if not article:
        state["errors"].append("Impact Analyzer: No cleaned article found in state.")
        return state
        
    print(f"\n[SUBAGENT] Impact Analyzer: Calculating market impact...")
    
    try:
        truncated_content = article["content"][:4000]
        prompt = get_stock_impact_prompt(truncated_content, state["entities"])
        response = query_groq(prompt)
        
        # Parse JSON defensively
        state["impacted_stocks"] = clean_and_parse_json_array(response)
        print(f"--> Mapped {len(state['impacted_stocks'])} stock impacts via LLM.")
        
    except Exception as e:
        print(f"[JSON PARSE WARNING]: LLM impact analysis failed ({e}). Generating default baseline impact.")
        
        # ─── GRACEFUL FALLBACK: Map a neutral baseline impact to prevent crashes ───
        fallback_impacts = []
        for entity in state.get("entities", []):
            if entity["category"] == "Company":
                fallback_impacts.append({
                    "symbol": entity["name"][:10].upper(), # Generate a dummy symbol
                    "confidence": 0.5,
                    "type": "direct",
                    "sentiment": "neutral",
                    "reasoning": "Article mentions company. LLM impact analysis was bypassed."
                })
        state["impacted_stocks"] = fallback_impacts
        print(f"--> Populated {len(state['impacted_stocks'])} baseline stock impacts.")
        
    return state