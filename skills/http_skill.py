import requests
from langchain.tools import tool
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_helper import truncate_or_save
@tool
def fetch_url_content(url: str) -> str:
    """
    Fetches the HTML or text content of a given HTTP/HTTPS URL.
    """
    try:
        response = requests.get(url.strip(), timeout=10)
        response.raise_for_status()
        content = response.text
        return truncate_or_save(content, max_length=3000, context_name="http_fetch")
    except Exception as e:
        return f"Error fetching URL: {e}"
