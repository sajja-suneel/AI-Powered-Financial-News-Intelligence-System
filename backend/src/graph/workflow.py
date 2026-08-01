# src/graph/workflow.py
from langgraph.graph import StateGraph, END
from src.graph.state import AgentState
from src.utils.logger import get_logger

logger = get_logger("workflow.master")

# Import node functions from our agent scripts
from src.agents.ingestion import ingestion_subagent
from src.agents.deduplication import deduplication_subagent
from src.agents.entity_extractor import extraction_subagent
from src.agents.impact_analyzer import impact_subagent
from src.agents.storage import finalizer_subagent

class MasterAgentGraph:
    """
    Encapsulates the construction, routing logic, and compilation of the
    LangGraph Multi-Agent news ingestion workflow.
    """

    @staticmethod
    def router(state: AgentState) -> str:
        """
        Evaluates the current state after deduplication.
        - If errors occurred: route directly to the finalizer to log them.
        - If duplicate identified: bypass entity extraction and go straight to storage.
        - Otherwise: continue to entity extractor.
        """
        if state.get("errors"):
            logger.warning("[MASTER ROUTER] Error logged. Bypassing downstream nodes.")
            return "finalation"
            
        if state.get("is_duplicate"):
            logger.info("[MASTER ROUTER] Duplicate identified. Bypassing extraction to go to finalizer.")
            return "finalation"
            
        # If the article is unique and has no entities extracted yet, continue sequence
        if not state.get("entities"):
            logger.info("[MASTER ROUTER] Article is unique. Routing to Extraction Node.")
            return "entity_extractor"
            
        # Default fall-through to finalizer
        return "finalation"

    @classmethod
    def compile_graph(cls):
        """
        Constructs, links, and compiles the multi-agent graph.
        """
        builder = StateGraph(AgentState)

        # 1. Register Subagent Nodes in the workflow
        builder.add_node("ingestion", ingestion_subagent)
        builder.add_node("deduplicator", deduplication_subagent)
        builder.add_node("entity_extractor", extraction_subagent)
        builder.add_node("impact_analyzer", impact_subagent)
        builder.add_node("finalation", finalizer_subagent)

        # 2. Set the News Ingestion Agent as the Entry Point
        builder.set_entry_point("ingestion")

        # 3. Register Transitions (Edges)
        builder.add_edge("ingestion", "deduplicator")

        # Define dynamic routing edge after deduplication
        builder.add_conditional_edges(
            "deduplicator",
            cls.router,
            {
                "finalation": "finalation",
                "entity_extractor": "entity_extractor"
            }
        )

        # Define static edges for the rest of the unique article analysis pipeline
        builder.add_edge("entity_extractor", "impact_analyzer")
        builder.add_edge("impact_analyzer", "finalation")
        builder.add_edge("finalation", END)

        # Compile and return application
        compiled_app = builder.compile()
        logger.info("[MASTER GRAPH] Multi-Agent Sequential Workflow Compiled successfully!")
        return compiled_app

# ----------------------------------------------------
# Module-level alias to keep main.py and other files backward-compatible
# ----------------------------------------------------
app = MasterAgentGraph.compile_graph()