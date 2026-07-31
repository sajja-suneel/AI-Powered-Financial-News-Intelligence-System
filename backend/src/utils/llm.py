# src/utils/llm.py
import os
from dotenv import load_dotenv
from groq import Groq

# Load environment variables
load_dotenv()

# Initialize the Groq Client
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set in your .env file.")

# Create the global client instance
client = Groq(api_key=GROQ_API_KEY)

# Use Llama 3 70B for high-precision parsing, or 8B for absolute fastest response times
# New line:
DEFAULT_MODEL = "llama-3.1-8b-instant"

def query_groq(prompt: str, model_name: str = DEFAULT_MODEL) -> str:
    """
    Helper function to send prompts to the Groq API.
    Returns the response text.
    """
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional financial news intelligence assistant. Answer queries exactly as requested in strict formats."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model=model_name,
            temperature=0.2, # Zero temperature ensures deterministic output (especially for JSON schemas)
        )
        # Extract response text
        return chat_completion.choices[0].message.content
        
    except Exception as e:
        print(f"[GROQ ERROR] API request failed: {e}")
        raise e