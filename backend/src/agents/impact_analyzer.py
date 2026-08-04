# src/agents/impact_analyzer.py
import json
import re
from src.graph.state import AgentState
from src.utils.llm import query_groq
from src.utils.prompts import get_stock_impact_prompt
from src.utils.logger import get_logger

logger = get_logger("agent.impact_analyzer")

class ImpactAnalyzerAgent:
    """
    Analyzes extracted entities and article context to determine stock tickers,
    market sentiments, and confidence scores using LLM logic.
    """

    @staticmethod
    def _clean_and_parse_json_array(raw_text: str) -> list:
        """
        Cleans markdown blocks and extracts the outermost JSON array [...]
        """
        text = raw_text.strip().replace("```json", "").replace("```", "")
        start_idx = text.find('[')
        end_idx = text.rfind(']')
        if start_idx == -1 or end_idx == -1:
            raise ValueError("No JSON array found in response.")
        return json.loads(text[start_idx:end_idx+1])

    @staticmethod
    def analyze_impact(state: AgentState) -> AgentState:
        """
        LangGraph Node function that assesses news impact on listed stocks and 
        writes stock sentiments and reasoning into the shared state.
        """
        if state.get("errors") or state.get("is_duplicate"):
            return state
            
        article = state.get("cleaned_article")
        if not article:
            state["errors"].append("Impact Analyzer: No cleaned article found in state.")
            return state
            
        logger.info("[SUBAGENT] Impact Analyzer: Calculating market impact...")
        
        try:
            truncated_content = article["content"][:4000]
            prompt = get_stock_impact_prompt(truncated_content, state["entities"])
            response = query_groq(prompt)
            
            # Parse JSON defensively
            state["impacted_stocks"] = ImpactAnalyzerAgent._clean_and_parse_json_array(response)
            logger.info(f"--> Mapped {len(state['impacted_stocks'])} stock impacts via LLM.")
            
        except Exception as e:
            logger.warning(f"[JSON PARSE WARNING]: LLM impact analysis failed ({e}). Generating default baseline impact.")
            
            # Graceful Fallback: Map a neutral baseline impact to prevent crashes
            fallback_impacts = []
            for entity in state.get("entities", []):
                cat = entity.get("category", "")
                if cat == "Company":
                    imp_type = "direct"
                    conf = 0.8
                elif cat == "Sector":
                    imp_type = "sector"
                    conf = 0.5
                elif cat == "Regulator":
                    imp_type = "regulatory"
                    conf = 0.2
                else:
                    continue
                
                # Generate a safe symbol candidate
                symbol_candidate = entity["name"].split()[0].upper()[:10]
                fallback_impacts.append({
                    "symbol": symbol_candidate,
                    "confidence": conf,
                    "type": imp_type,
                    "sentiment": "neutral",
                    "reasoning": f"Baseline fallback neutral assessment for {cat} entity: '{entity['name']}'."
                })
            state["impacted_stocks"] = fallback_impacts
            logger.info(f"--> Populated {len(state['impacted_stocks'])} baseline stock impacts.")
            
        return state

# ----------------------------------------------------
# Module-level alias to keep other files backward-compatible
# ----------------------------------------------------
impact_subagent = ImpactAnalyzerAgent.analyze_impact