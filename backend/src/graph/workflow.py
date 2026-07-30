# src/graph/workflow.py
from langgraph.graph import StateGraph, END
from src.graph.state import AgentState

# Import node functions from our agent scripts
from src.agents.ingestion import ingestion_subagent
from src.agents.deduplication import deduplication_subagent
from src.agents.entity_extractor import extraction_subagent
from src.agents.impact_analyzer import impact_subagent
from src.agents.storage import finalizer_subagent

# 1. Master Agent Routing Logic
def master_router(state: AgentState) -> str:
    """
    Evaluates the state after deduplication.
    - If errors occurred: route directly to the finalizer to log them.
    - If duplicate identified: bypass entity extraction and go straight to storage.
    - Otherwise: continue to entity extractor.
    """
    if state.get("errors"):
        print("[MASTER ROUTER] Error logged. Bypassing downstream nodes.")
        return "finalation"
        
    if state.get("is_duplicate"):
        print("[MASTER ROUTER] Duplicate identified. Bypassing extraction to go to finalizer.")
        return "finalation"
        
    # If the article is unique and has no entities extracted yet, continue sequence
    if not state.get("entities"):
        print("[MASTER ROUTER] Article is unique. Routing to Extraction Node.")
        return "entity_extractor"
        
    # Default fall-through to finalizer
    return "finalation"

# 2. Build the Graph
builder = StateGraph(AgentState)

# Register Subagent Nodes in the workflow
builder.add_node("ingestion", ingestion_subagent)
builder.add_node("deduplicator", deduplication_subagent)
builder.add_node("entity_extractor", extraction_subagent)
builder.add_node("impact_analyzer", impact_subagent)
builder.add_node("finalation", finalizer_subagent)

# Set the News Ingestion Agent as the Entry Point
builder.set_entry_point("ingestion")

# 3. Register Transitions (Edges)
builder.add_edge("ingestion", "deduplicator")

# Define the dynamic routing edge after the Deduplication Agent runs
builder.add_conditional_edges(
    "deduplicator",
    master_router,
    {
        "finalation": "finalation",
        "entity_extractor": "entity_extractor"
    }
)

# Define static edges for the rest of the unique article analysis pipeline
builder.add_edge("entity_extractor", "impact_analyzer")
builder.add_edge("impact_analyzer", "finalation")
builder.add_edge("finalation", END)

# Compile Graph
app = builder.compile()
print("[MASTER GRAPH] Multi-Agent Sequential Workflow Compiled successfully!")