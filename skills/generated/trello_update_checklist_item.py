import os
import requests
from smolagents import tool

@tool
def trello_update_checklist_item(card_id: str, item_name: str, state: str = "complete") -> str:
    """
    Updates the state of a checklist item on a Trello card.
    
    Args:
        card_id: The ID of the Trello card.
        item_name: The exact name of the checklist item to update.
        state: The state to set ('complete' or 'incomplete').
    """
    api_key = os.environ.get("TRELLO_KEY")
    token = os.environ.get("TRELLO_TOKEN")
    
    if not api_key or not token:
        return "Error: TRELLO_KEY or TRELLO_TOKEN environment variables not set."
    
    url = f"https://api.trello.com/1/cards/{card_id}/checklists"
    query = {"key": api_key, "token": token}
    response = requests.get(url, params=query)
    
    if response.status_code != 200:
        return f"Error fetching checklists: {response.text}"
        
    checklists = response.json()
    
    target_item = None
    
    for cl in checklists:
        for item in cl.get("checkItems", []):
            if item["name"].lower() == item_name.lower():
                target_item = item
                break
        if target_item:
            break
            
    if not target_item:
        return f"Error: Checklist item '{item_name}' not found on card {card_id}."
        
    update_url = f"https://api.trello.com/1/cards/{card_id}/checkItem/{target_item['id']}"
    update_query = {
        "key": api_key,
        "token": token,
        "state": state
    }
    
    update_res = requests.put(update_url, params=update_query)
    if update_res.status_code == 200:
        return f"Success: Item '{item_name}' marked as {state}."
    else:
        return f"Error updating item: {update_res.text}"
