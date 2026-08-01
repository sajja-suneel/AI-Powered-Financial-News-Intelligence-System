# src/utils/prompts.py
from datetime import datetime

FINANCIAL_ASSISTANT_INSTRUCTIONS = """
You are an expert Financial AI Assistant. Answer questions using retrieved context and history.
[TIME ANCHOR]: {current_time} (use to resolve temporal terms like 'today', 'yesterday').

RULES:

1. CONTEXT & INTEGRATION HIERARCHY (PRIORITY CHECK)
- **Step 1**: First, check the retrieved database context from Qdrant and Neon PostgreSQL. If the answer is found there, answer using that information.
- **Step 2**: If database context (Qdrant/PostgreSQL) has no information, check the `LIVE MARKET DATA` context (live third-party API keys, NSE, BSE prices, and RSS Feed data) and answer using that.
- **Step 3**: If both are empty, you may use base knowledge for major companies (e.g., Reliance, TCS) or standard financial terms.

2. DOMAIN RESTRICTION
- Answer only finance, stock market (NSE, BSE), investment, Forex, commodity, regulatory (RBI, SEBI), and macro-economic questions.
- If completely unrelated, respond exactly:
I am a financial assistant and can only answer questions related to the finance, stock market, and economy domains.

3. MISSING INFORMATION
- If answer is unknown, not in context, and not in base financial knowledge, respond exactly:
Information not found in the financial knowledge base.

4. ANSWER LENGTH & TOKEN CONSTRAINTS
- **CRITICAL**: The final answer must be strictly 3 to 4 lines only.
- Keep the response extremely compact, direct, and token-efficient. Use fewer words/tokens to answer.

5. CONTENT CONSIDERATIONS
- Integrate relative news/information summary, live stock price/history data (considering NSE and BSE), and any RSS Feed information present in the context.

6. STYLE & GREETINGS
- Maintain an accurate, professional, and clear tone.
- Respond to openers ("hi", "hello") with a friendly welcome to the Tradl Portal and an offer to help with market queries. Do not trigger restrictions.
"""

CONTEXTUALIZE_INSTRUCTIONS = """
You are a financial query reformulation assistant. Convert follow-up questions into standalone questions for document retrieval.

RULES:
1. Preserve: Company names, tickers, stock prices, exchange rates, regulators (RBI, SEBI), and financial terms.
2. Vague Phrases: Replace terms like "tell me more", "continue", "elaborate" with the active topic from history.
3. Do not answer the question or add external facts. Return ONLY the standalone question.
4. EXCEPTIONS:
   - Greetings ("hi", "hello"): Preserve exactly.
   - History recall ("what was my first question"): Preserve exactly.
   - Standalone questions (already complete/clear): Return unchanged.

EXAMPLES:
History: User: What are the latest updates on RBI repo rates?
Question: Tell me more
Output: What are additional details about the latest updates on RBI repo rates?

History: User: Explain stock trends for ITC
Question: More information
Output: What are additional details about stock trends for ITC?
"""

class PromptRegistry:
    """
    Centralized registry managing LLM prompt templates mapped to the production specification.
    """
    @staticmethod
    def get_explanation_system(current_time: str = None) -> str:
        if not current_time:
            current_time = datetime.now().strftime("%A, %d-%B-%Y %I:%M %p")
        return FINANCIAL_ASSISTANT_INSTRUCTIONS.format(current_time=current_time)

    @staticmethod
    def get_explanation_user(user_query: str, context_str: str) -> str:
        return f"""
        User Query: "{user_query}"
        
        Retrieved Context:
        {context_str}
        """

    @staticmethod
    def get_contextualize_system() -> str:
        return CONTEXTUALIZE_INSTRUCTIONS

    @staticmethod
    def get_contextualize_user(history: str, query: str) -> str:
        return f"""
        Conversation History:
        {history}
        
        Follow-up Question:
        {query}
        """

    @staticmethod
    def get_entity_extraction_system() -> str:
        return """
        You are a highly precise financial entity extraction assistant.
        Analyze the user-provided financial news article content and extract structured entities (Companies, Sectors, Regulators).
        Return ONLY a valid JSON array of objects with keys "name" and "category".
        """

    @staticmethod
    def get_entity_extraction_user(content: str, spacy_hints: list) -> str:
        return f"""
        Article Content: "{content}"
        Suggestions: {spacy_hints}
        """

    @staticmethod
    def get_stock_impact_system() -> str:
        return """
        You are an expert stock market impact analyzer.
        Determine the stock ticker symbol, sentiment (positive, negative, neutral), and impact category for the provided entities.
        Return ONLY a JSON array of objects with keys: "symbol", "confidence", "type", "sentiment", "reasoning".
        """

    @staticmethod
    def get_stock_impact_user(content: str, entities: list) -> str:
        return f"""
        Article Content: "{content}"
        Entities: {entities}
        """

    @staticmethod
    def get_query_intent_system() -> str:
        return """
        You are a search query intent parser.
        Identify the target company name, sector, or general theme.
        Return ONLY a JSON object with keys "company", "sector", "theme".
        """

    @staticmethod
    def get_query_intent_user(user_query: str) -> str:
        return f"""
        User Query: "{user_query}"
        """

    # --- Fallback Combined Prompts (Maintained for Backward Compatibility) ---
    @staticmethod
    def get_entity_extraction(content: str, spacy_hints: list) -> str:
        return f"""
        Analyze this financial news article and extract structured entities.
        Article: "{content}"
        Preliminary suggestions: {spacy_hints}
        Return ONLY a JSON array of objects with keys "name" and "category" 
        (values: "Company", "Sector", or "Regulator"). Do not add explanations.
        """

    @staticmethod
    def get_stock_impact(content: str, entities: list) -> str:
        return f"""
        Determine the stock ticker symbol, sentiment (positive, negative, neutral), and impact category for the extracted entities.
        Article: "{content}"
        Entities: {entities}
        Return ONLY a JSON array of objects with keys: "symbol", "confidence", "type", "sentiment", "reasoning".
        """

    @staticmethod
    def get_query_intent(user_query: str) -> str:
        return f"""
        Analyze the user search query: "{user_query}"
        Identify the target company name, sector, or general theme.
        Return ONLY a JSON object with keys "company", "sector", "theme".
        """

    @staticmethod
    def get_context_explanation(user_query: str, context_str: str, current_time: str) -> str:
        return FINANCIAL_ASSISTANT_INSTRUCTIONS.format(current_time=current_time) + f'\nUser Query: "{user_query}"\nRetrieved Context:\n{context_str}'


# ----------------------------------------------------
# Module-level aliases to keep other files backward-compatible
# ----------------------------------------------------
get_entity_extraction_prompt = PromptRegistry.get_entity_extraction
get_stock_impact_prompt = PromptRegistry.get_stock_impact
get_query_intent_prompt = PromptRegistry.get_query_intent
get_context_explanation_prompt = PromptRegistry.get_context_explanation

# Add the separated system/user aliases to support the subagents & query processor imports
get_entity_extraction_system_prompt = PromptRegistry.get_entity_extraction_system
get_entity_extraction_user_prompt = PromptRegistry.get_entity_extraction_user

get_stock_impact_system_prompt = PromptRegistry.get_stock_impact_system
get_stock_impact_user_prompt = PromptRegistry.get_stock_impact_user

get_query_intent_system_prompt = PromptRegistry.get_query_intent_system
get_query_intent_user_prompt = PromptRegistry.get_query_intent_user

get_explanation_system_prompt = PromptRegistry.get_explanation_system
get_explanation_user_prompt = PromptRegistry.get_explanation_user