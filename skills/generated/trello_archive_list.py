import os
import requests
from smolagents import tool

@tool
def trello_archive_list(list_id: str) -> str:
    """
    Archive (close) a Trello list by its ID.
    
    Args:
        list_id: The ID of the Trello list to archive.
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.environ.get("TRELLO_KEY")
    token = os.environ.get("TRELLO_TOKEN")
    
    if not api_key or not token:
        return "Error: TRELLO_KEY or TRELLO_TOKEN not found in environment."
        
    url = f"https://api.trello.com/1/lists/{list_id}/closed"
    query = {
        'key': api_key,
        'token': token,
        'value': 'true'
    }
    
    response = requests.put(url, params=query)
    
    if response.status_code == 200:
        return f"List {list_id} archived."
    return f"Error {response.status_code}: {response.text}"
