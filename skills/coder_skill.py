import os
import json
from llm_client import llm
import history_manager

def execute(user_message: str, session_id: str = "default") -> str:
    """
    Translates the user's request into file creation/modification.
    """
    past_messages = history_manager.get_history(session_id, limit=5)
    
    history_text = ""
    if past_messages:
        history_text = "Conversation History:\n"
        for msg in past_messages:
            history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"
        history_text += "---\n\n"

    system_prompt = """You are an expert AI coder and file manager.
The user wants you to create or write code to a file.
Based on the user's request and conversation history, you must output a raw JSON object (without markdown code blocks if possible).
The JSON must have exactly two keys:
1. "filename": The path to the file to create/write (e.g., "scheduler.py" or "/path/to/script.sh").
2. "content": The complete code or text to write into the file.

Output ONLY valid JSON. Example:
{
  "filename": "hello.py",
  "content": "print('Hello World')\\n"
}
"""
    
    full_prompt = history_text + "User: " + user_message
    
    response = llm.ask(prompt=full_prompt, system_prompt=system_prompt)
    
    try:
        # Clean up response in case LLM wrapped it in markdown
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
            
        data = json.loads(cleaned.strip())
        filename = data.get("filename", "")
        content = data.get("content", "")
        
        if not filename:
            return "Maaf, saya tidak dapat menentukan nama file dari permintaan Anda."
            
        # Ensure directory exists
        abs_path = os.path.abspath(filename)
        dir_name = os.path.dirname(abs_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return f"Berhasil membuat/menyimpan file: `{filename}`\n\nIsi file ({len(content.splitlines())} baris) telah ditulis ke sistem Anda."
        
    except json.JSONDecodeError:
        return f"Gagal mengekstrak JSON dari respons LLM. Respons: \n{response}"
    except Exception as e:
        return f"Terjadi kesalahan saat menulis file: {e}"
