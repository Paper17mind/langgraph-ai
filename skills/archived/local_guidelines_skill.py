import os
from langchain_core.tools import tool

# Ensure guidelines directory exists
GUIDELINES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "guidelines")
os.makedirs(GUIDELINES_DIR, exist_ok=True)

@tool
def list_guidelines() -> str:
    """
    Lists all available local markdown guideline files in the guidelines/ directory.
    Returns the filenames and a short description (the first line of the file) if available.
    Use this to see if there are any specific best practices or coding rules provided by the user.
    """
    if not os.path.exists(GUIDELINES_DIR):
        return "Directory 'guidelines/' tidak ditemukan."
        
    files = [f for f in os.listdir(GUIDELINES_DIR) if f.endswith('.md')]
    if not files:
        return "Belum ada file pedoman (.md) yang tersimpan di dalam folder 'guidelines/'."
        
    result = []
    for f in files:
        file_path = os.path.join(GUIDELINES_DIR, f)
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                first_line = file.readline().strip()
                result.append(f"- {f}: {first_line}")
        except Exception as e:
            result.append(f"- {f}: (Gagal membaca deskripsi: {e})")
            
    return "Daftar Pedoman Tersedia:\n" + "\n".join(result)

@tool
def read_guideline(filename: str) -> str:
    """
    Reads the full content of a specific markdown guideline file.
    Args:
        filename: The exact name of the file (e.g., 'react-best-practices.md')
    """
    file_path = os.path.join(GUIDELINES_DIR, filename)
    if not os.path.exists(file_path):
        return f"Error: File pedoman '{filename}' tidak ditemukan di folder 'guidelines/'."
        
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return f"--- ISI PEDOMAN: {filename} ---\n\n{content}"
    except Exception as e:
        return f"Error membaca file '{filename}': {e}"
