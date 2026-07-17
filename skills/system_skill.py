import subprocess
from langchain.tools import tool
import sys
import os

# Add root directory to sys.path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.text_helper import truncate_or_save

@tool
def execute_system_command(command: str) -> str:
    """
    Executes a bash/system command on the local machine and returns the output or error.
    Use this to run terminal commands (e.g., ls, df, curl, etc.).
    IMPORTANT: Do NOT use this to run heavy installations like `playwright install` or `docker pull`.
    IMPORTANT: If using curl with URLs containing '&', you MUST wrap the URL in quotes!
    """
    
    # Deteksi perintah instalasi berat yang sudah pasti lama
    heavy_commands = [
        "playwright install", 
        "apt-get install", 
        "apt install",
        "docker pull"
    ]
    command_lower = command.lower()
    for heavy in heavy_commands:
        if heavy in command_lower:
            return f"BLOCKED: Perintah '{command}' terdeteksi sebagai instalasi/unduhan berat. JANGAN diulang. Beritahu pengguna untuk menjalankannya secara manual di terminal mereka."

    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True, timeout=50)
        output = result.stdout.strip()
        if not output:
            output = "Command executed successfully with no output."
        
        return truncate_or_save(output, max_length=2000, context_name="system_cmd")

    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 50 seconds. JANGAN DIULANG (DO NOT RETRY). Perintah ini memakan waktu terlalu lama. Beritahu pengguna untuk menjalankannya secara manual di terminal mereka."
    except Exception as e:
        return f"Error executing command: {e}"
