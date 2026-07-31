# src/utils/prompts.py

def get_entity_extraction_prompt(content: str, spacy_hints: list) -> str:
    """Prompt template for the Entity Extraction Subagent"""
    return f"""
    Analyze this financial news article and extract structured entities.
    Article: "{content}"
    Preliminary suggestions: {spacy_hints}
    
    Return ONLY a JSON array of objects with keys "name" and "category" 
    (values: "Company", "Sector", or "Regulator"). Do not add explanations.
    
    Example:
    [
      {{"name": "HDFC Bank", "category": "Company"}},
      {{"name": "Banking", "category": "Sector"}}
    ]
    """

def get_stock_impact_prompt(content: str, entities: list) -> str:
    """Prompt template for the Stock Impact Analysis Subagent"""
    return f"""
    Determine the stock ticker symbol, sentiment (positive, negative, neutral), and impact category for the extracted entities.
    Article: "{content}"
    Entities: {entities}
    
    Assign confidence parameters based on these rules:
    - Direct mention of the company: 1.0
    - Sector-wide news: 0.7
    - Regulatory policy changes (e.g. interest rates): 0.8
    
    Return ONLY a JSON array of objects with keys: "symbol", "confidence", "type" (direct/sector-wide/regulatory), "sentiment", "reasoning".
    Do not add any explanations or markdown.
    """

def get_query_intent_prompt(user_query: str) -> str:
    """Prompt template for the Query Processor to parse search intent"""
    return f"""
    Analyze the user search query: "{user_query}"
    Identify the target company name, sector, or general theme.
    
    Return ONLY a JSON object with keys "company", "sector", "theme". Do not include any explanations.
    """

# src/utils/prompts.py

def get_context_explanation_prompt(user_query: str, context_str: str, current_time: str) -> str:
    """
    Directs the LLM to answer ONLY the user's question directly, using the provided context,
    without adding unrelated facts or boilerplate.
    """
    return f"""
    You are an expert Financial Intelligence Analyst.
    
    [TEMPORAL CONTEXT]: The current local system date and time is: {current_time}.
    Use this date/time anchor to resolve temporal references (like 'today', 'yesterday').
    
    User Query: "{user_query}"
    
    Matching Database Context:
    {context_str}
    
    Rules for answering:
    1. Answer the User Query DIRECTLY and CONCISELY.
    2. STRICT RELEVANCE: Only include details, stocks, rates, or facts that directly answer the query. If the context contains details about USD/INR rates, gold, or other companies that have NOTHING to do with the query, DO NOT include them.
    3. If the context does not contain the answer, respond with "I don't have information about that."
    4. Formatting: Output the answer in a clean, readable markdown format. Only include relevant sections.
    """