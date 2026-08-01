# src/utils/llm.py
import os
from dotenv import load_dotenv
from groq import Groq
from src.utils.logger import get_logger

logger = get_logger("utils.llm")

# Load environment variables
load_dotenv()

class LlmEngine:
    """
    Manages the Groq LLM client connection and provides static helper functions
    to execute high-precision chat completion queries.
    """
    _client_instance = None
    DEFAULT_MODEL = "llama-3.1-8b-instant"

    @classmethod
    def get_client(cls) -> Groq:
        """
        Returns the cached Groq client instance, initializing it on the first call.
        """
        if cls._client_instance is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY is not set in your .env file.")
            cls._client_instance = Groq(api_key=api_key)
        return cls._client_instance

    @classmethod
    def query(cls, user_prompt: str, system_prompt: str = None, model_name: str = DEFAULT_MODEL) -> str:
        """
        Sends messages to the Groq API and returns the generated text.
        Accepts an optional custom system prompt. Uses temperature 0.0 for structured JSON accuracy.
        """
        client = cls.get_client()
        
        messages = []
        # 1. Use custom system prompt if provided, otherwise fallback to default
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({
                "role": "system",
                "content": "You are a professional financial news intelligence assistant. Answer queries exactly as requested in strict formats."
            })
            
        # 2. Add user prompt
        messages.append({"role": "user", "content": user_prompt})
        
        try:
            chat_completion = client.chat.completions.create(
                messages=messages,
                model=model_name,
                temperature=0.2  # Ensures deterministic output for JSON schemas and filters
            )
            return chat_completion.choices[0].message.content
            
        except Exception as e:
            logger.error(f"[GROQ ERROR] API query failed: {e}")
            raise e

# ----------------------------------------------------
# Module-level alias to keep other files backward-compatible
# ----------------------------------------------------
query_groq = LlmEngine.query