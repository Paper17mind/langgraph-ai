from ddgs import DDGS
from langchain.tools import tool

@tool
def search_duckduckgo(query: str) -> str:
    """
    Searches DuckDuckGo for the given query and returns the top results.
    """
    try:
        ddgs = DDGS()
        results = list(ddgs.text(query.strip(), max_results=3))
        if not results:
            return "No results found."
            
        search_context = "\n\n".join([f"Title: {r['title']}\nSnippet: {r['body']}\nURL: {r['href']}" for r in results])
        return search_context
    except Exception as e:
        return f"Search error: {e}"
