import os
import sys
from langchain.tools import tool

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.memory_db import memory_db

@tool
def remember_fact(fact: str = "", key: str = "", value: str = "") -> str:
    """Save info or key-value fact to long-term memory."""
    if not fact:
        if key and value:
            fact = f"{key}: {value}"
        elif key:
            fact = key
        elif value:
            fact = value
        else:
            return "Error: Memori yang akan disimpan tidak boleh kosong."
    return memory_db.save_fact(fact)

@tool
def recall_facts(query: str) -> str:
    """Search past memory by semantic query."""
    return memory_db.search_facts(query)

@tool
def forget_fact(fact_text: str) -> str:
    """Delete a specific memory/fact from the long-term database by matching a substring."""
    return memory_db.forget_fact(fact_text)
