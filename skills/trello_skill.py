#!/usr/bin/env python3
# /var/www/projects/ai-telebot/skills/trello_skill.py
import os, json, urllib.request, urllib.parse, sys
from langchain.tools import tool

TRELLO_KEY   = os.getenv("TRELLO_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
BASE_URL = "https://api.trello.com/1"

def _request(method: str, path: str, params: dict = None, data: dict = None):
    if not TRELLO_KEY or not TRELLO_TOKEN:
        raise RuntimeError("TRELLO_KEY/TRELLO_TOKEN not set")
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    if params:
        auth.update(params)
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(auth)}"
    req = urllib.request.Request(url, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(data).encode()
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)

@tool
def trello_create_board(name: str, description: str = "") -> str:
    """Create a new Trello board with the given name and description."""
    board = _request("POST", "/boards", {"name": name, "desc": description})
    return f"✅ board created – id:{board['id']} url:{board['url']}"

@tool
def trello_add_list(board_id: str, list_name: str) -> str:
    """Add a list to an existing Trello board with the given board ID and list name."""
    lst = _request("POST", "/lists", {"name": list_name, "idBoard": board_id})
    return f"✅ list added – id:{lst['id']}"

@tool
def trello_add_card(list_id: str, card_name: str, desc: str = "") -> str:
    """Add a card to a Trello list with the given list ID, card name, and description."""
    card = _request("POST", "/cards", {"idList": list_id, "name": card_name, "desc": desc})
    return f"✅ card created – id:{card['id']} url:{card['url']}"

@tool
def trello_get_board(board_id: str) -> str:
    """Get a clean text summary of a Trello board (including its lists and cards) with the given board ID."""
    try:
        board = _request("GET", f"/boards/{board_id}", {"lists": "all", "list_fields": "name", "cards": "all"})
        
        # Create a concise text summary instead of returning raw JSON
        summary = f"Board Name: {board.get('name', 'Unknown')}\n"
        summary += f"Board ID: {board.get('id', board_id)}\n\n"
        
        lists = board.get('lists', [])
        cards = board.get('cards', [])
        
        for lst in lists:
            summary += f"📋 List: {lst.get('name')} (ID: {lst.get('id')})\n"
            list_cards = [c for c in cards if c.get('idList') == lst.get('id')]
            if not list_cards:
                summary += "   (Tidak ada kartu)\n"
            for card in list_cards:
                summary += f"   - 💳 {card.get('name')} (ID: {card.get('id')})\n"
            summary += "\n"
            
        return summary.strip()
    except Exception as e:
        return f"Gagal mengambil board: {e}"

if __name__ == "__main__":
    try:
        # Use .run() because @tool wraps the function
        print(trello_create_board.run("Demo board from AI‑skill"))
    except Exception as e:
        print(f"⚠️ {e}")
        sys.exit(0)
