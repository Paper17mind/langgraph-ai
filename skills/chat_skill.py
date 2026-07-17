from core.llm_client import llm
from core import history_manager

def execute(user_message: str, session_id: str = "default") -> str:
    """
    Handles general chat using the configured chat model, with history.
    """
    past_messages = history_manager.get_history(session_id, limit=10)
    
    history_text = ""
    if past_messages:
        history_text = "Here is the recent conversation history:\n"
        for msg in past_messages:
            history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"
        history_text += "---\n\n"

    system_prompt = "You are a helpful, smart, and lightweight AI assistant running on the user's desktop."
    full_prompt = history_text + "User: " + user_message
    
    response = llm.ask(prompt=full_prompt, system_prompt=system_prompt)
    return response
