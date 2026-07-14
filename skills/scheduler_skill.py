from llm_client import llm
import history_manager

def execute(user_message: str, session_id: str = "default") -> str:
    """
    Handles scheduling requests conversationally.
    """
    past_messages = history_manager.get_history(session_id, limit=5)
    
    history_text = ""
    if past_messages:
        history_text = "Conversation History:\n"
        for msg in past_messages:
            history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"
        history_text += "---\n\n"

    system_prompt = """You are a helpful AI scheduling assistant. 
Your job is to handle scheduling-related questions and commands.
- Jika user hanya bertanya apakah kamu bisa membuat jadwal/scheduler, jawablah dengan natural (misal: "Ya, saya bisa membuatkan jadwal untuk Anda! Apa yang ingin Anda jadwalkan?").
- Jika user secara eksplisit meminta membuat jadwal (misal: "ingatkan saya 5 menit lagi"), jawablah dengan natural bahwa jadwal tersebut telah dicatat (Catatan: untuk saat ini, fitur eksekusi background masih dalam tahap simulasi).
- Selalu gunakan bahasa yang ramah dan sesuai dengan bahasa user (Bahasa Indonesia)."""
    
    full_prompt = history_text + "User: " + user_message
    
    response = llm.ask(prompt=full_prompt, system_prompt=system_prompt)
    
    return response
