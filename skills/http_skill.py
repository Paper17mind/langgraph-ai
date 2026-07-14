import requests
from llm_client import llm
import json

def execute(user_message: str, session_id: str = "default") -> str:
    """
    Uses LLM to extract a URL from the user message, fetches it, and summarizes the result if needed.
    """
    # Use LLM to extract URL
    system_prompt = """You are a URL extractor. Extract the main URL from the user's message.
Return ONLY the raw URL starting with http:// or https://. Do not return any other text.
If no URL is found, return 'NO_URL'."""
    
    url = llm.ask(prompt=user_message, system_prompt=system_prompt)
    
    if url.strip() == "NO_URL" or not url.startswith("http"):
        return "I couldn't find a valid URL in your request."
    
    try:
        response = requests.get(url.strip(), timeout=10)
        response.raise_for_status()
        content = response.text
        
        # If content is huge, we might want to truncate or summarize it
        if len(content) > 2000:
            truncated = content[:2000] + "...\n[Content truncated]"
            return f"Fetched {url}:\n\n```\n{truncated}\n```"
        return f"Fetched {url}:\n\n```\n{content}\n```"
    except Exception as e:
        return f"Error fetching {url}: {e}"
