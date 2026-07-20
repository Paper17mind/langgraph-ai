import os
import sys
from langchain.tools import tool

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.memory_db import memory_db

@tool
def remember_fact(fact: str) -> str:
    """Save info to long-term memory."""
    return memory_db.save_fact(fact)

@tool
def recall_facts(query: str) -> str:
    """Search past memory by semantic query."""
    return memory_db.search_facts(query)
