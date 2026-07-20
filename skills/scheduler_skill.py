import os
from langchain.tools import tool
from core import scheduler_db

@tool
def schedule_task(task_description: str, delay_seconds: int) -> str:
    """Schedule a background task/reminder."""
    session_id = os.getenv("CURRENT_SESSION_ID", "default")
    chat_id = os.getenv("CURRENT_CHAT_ID", session_id)
    scheduler_db.add_schedule(chat_id, task_description, delay_seconds)
    
    return f"Task '{task_description}' has been successfully scheduled to run in {delay_seconds} seconds."
