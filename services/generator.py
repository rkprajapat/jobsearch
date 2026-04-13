"""
LLM response generation service using litellm for multiple provider support.
"""
import os
from dotenv import load_dotenv
import litellm

load_dotenv()

# Configuration with sensible defaults
LLM_CONFIG = {
    "base_url": os.getenv("LLM_SERVER_BASE_URL", "http://localhost:8080/v1"),
    "model": os.getenv("LLM_SERVER_MODEL", "gemma-4"),
    "api_key": os.getenv("LLM_SERVER_API_KEY", "not-needed"),
}


def generate_response(prompt: str) -> str:
    """
    Generate a response from configured LLM endpoint.

    Args:
        prompt: The input prompt for generation.

    Returns:
        Generated response text, empty string on error.
        
    Raises:
        ValueError: If prompt is empty.
    """
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")
    
    try:
        response = litellm.completion(
            model=f"openai/{LLM_CONFIG['model']}",
            api_base=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"],
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""
    
    except Exception as e:
        print(f"LLM generation error: {e}")
        raise
