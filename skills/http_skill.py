import requests
from langchain.tools import tool

@tool
def fetch_url_content(url: str) -> str:
    """
    Fetches the HTML or text content of a given HTTP/HTTPS URL.
    """
    try:
        response = requests.get(url.strip(), timeout=10)
        response.raise_for_status()
        content = response.text
        if len(content) > 3000:
            return content[:3000] + "\n...[TRUNCATED]"
        return content
    except Exception as e:
        return f"Error fetching URL: {e}"
