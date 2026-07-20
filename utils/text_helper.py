import os
import time
from datetime import datetime

def truncate_or_save(content: str, max_length: int = 2000, context_name: str = "tool_output") -> str:
    """
    Checks if a string is too long. If it is, saves the full content to a file
    and returns a truncated version with a helpful note for the LLM.
    """
    if not isinstance(content, str):
        content = str(content)
        
    if len(content) <= max_length:
        return content
        
    # Generate a safe filename
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{context_name}_{timestamp}.txt"
    filepath = os.path.join(logs_dir, filename)
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
        preview = content[:max_length]
        warning = f"\n\n... [OUTPUT TRUNCATED: Panjang teks melebihi {max_length} karakter. Data asli yang lengkap telah disimpan di {filepath}. Jika Anda butuh melihat detail lengkapnya, Anda bisa membacanya menggunakan tool file reader.]"
        
        return preview + warning
    except Exception as e:
        # If saving fails, just return truncated text
        return content[:max_length] + f"\n\n... [OUTPUT TRUNCATED: Panjang teks melebihi {max_length} karakter.]"
