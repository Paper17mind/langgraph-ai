import os
import requests
from skills.base_skill import tool

@tool
def trello_move_card(card_id: str, list_id: str) -> str:
    """Move a Trello card to a different list.
    Requires card_id and target list_id."""
    key = os.getenv("TRELLO_KEY", "c43b7ebcd8c04dc577e2e5ef9ca08eab")
    token = os.getenv("TRELLO_TOKEN", "ATTAd829945a7e8aed55e71e0e93b7ecfec6c5a5da816bc703c6d97958afb46fe63aEB685740")
    
    url = f"https://api.trello.com/1/cards/{card_id}"
    query = {
        'key': key,
        'token': token,
        'idList': list_id
    }
    
    response = requests.put(url, params=query)
    if response.status_code == 200:
        return f"Success moving card {card_id} to list {list_id}"
    return f"Error: {response.status_code} - {response.text}"
