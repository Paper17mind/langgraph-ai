from duckduckgo_search import DDGS
from llm_client import llm

def execute(user_message: str, session_id: str = "default") -> str:
    """
    Uses LLM to generate a search query, searches DDG, and then uses LLM to summarize the result.
    """
    # 1. Generate search query
    query_prompt = """You are a search query generator. 
Extract the core search terms from the user's message.
Return ONLY the search query. Do not return any other text or quotes."""
    
    query = llm.ask(prompt=user_message, system_prompt=query_prompt)
    
    if not query.strip():
        return "Couldn't generate a search query."
        
    try:
        # 2. Search DuckDuckGo
        with DDGS() as ddgs:
            results = list(ddgs.text(query.strip(), max_results=3))
            
        if not results:
            return f"No results found for: {query}"
            
        # 3. Format results and summarize
        search_context = "\n\n".join([f"Title: {r['title']}\nSnippet: {r['body']}\nURL: {r['href']}" for r in results])
        
        summary_prompt = f"""You are a helpful assistant. Answer the user's original message based on the following search results.
If the search results don't answer the question, say so. Include relevant links.

Search Results:
{search_context}
"""
        
        summary = llm.ask(prompt=user_message, system_prompt=summary_prompt)
        return summary
        
    except Exception as e:
        return f"Error during web search: {e}"
