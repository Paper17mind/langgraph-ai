import os
import requests
from smolagents import tool

@tool
def trello_move_card(card_id: str, list_id: str) -> str:
    """
    Moves a Trello card to a different list.
    
    Args:
        card_id: The ID of the Trello card.
        list_id: The ID of the destination list.
    """
    api_key = os.environ.get("TRELLO_KEY")
    token = os.environ.get("TRELLO_TOKEN")
    
    if not api_key or not token:
        return "Error: TRELLO_KEY or TRELLO_TOKEN environment variables not set."
    
    url = f"https://api.trello.com/1/cards/{card_id}"
    query = {
        "key": api_key,
        "token": token,
        "idList": list_id
    }
    
    response = requests.put(url, params=query)
    
    if response.status_code == 200:
        return f"Success: Card {card_id} moved to list {list_id}."
    else:
        return f"Error moving card: {response.text}"
