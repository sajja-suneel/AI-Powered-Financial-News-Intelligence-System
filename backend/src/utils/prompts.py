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

def get_context_explanation_prompt(user_query: str, context_str: str) -> str:
    """
    Directs the LLM to synthesize matching context into a premium, 
    structured financial intelligence report. Supports fallback general knowledge.
    """
    return f"""
    You are an expert Financial Intelligence Analyst.
    Your task is to answer the user query: "{user_query}"
    
    Using the matching database context below:
    {context_str}
    
    You must format your final response strictly using the following structure:

    ### 📊 Executive Summary
    - [Summarize and explain the requested information directly in 3 to 5 lines. If the database context does not contain the direct answer, you MUST use your own pre-trained financial knowledge to answer the user's question fully and accurately. Clearly note if you are supplementing with general market knowledge.]

    ### 📈 Market Sentiment & Impact
    - **Asset Impacted**: [Identify target stocks/indices, e.g. NIFTY 50, SBI, HDFC]
    - **Sentiment Direction**: [Positive / Negative / Neutral]
    - **Impact Factor**: [Briefly explain the driver or general index behavior]

    ### 🔍 Key Supporting Facts
    - [Fact 1: If using general knowledge, list the top answers directly (e.g. the top 5 company names and details). If using context, extract numbers from context.]
    - [Fact 2: Additional supporting data or general index facts]

    ### 📑 References
    - Source: [Identify document sources or 'General Financial Knowledge']
    - Link: [Include clean URL links if available, or official exchange links like https://www.nseindia.com]
    
    Rules:
    - Never mention website boilerplate, sitemap links, or navigation buttons.
    - Keep tone professional, objective, and analytical.
    - If the user query asks for a list (like Top 5 Companies), you must list those 5 items clearly in the Executive Summary or Key Supporting Facts using your pre-trained knowledge if the database context is empty.
    """