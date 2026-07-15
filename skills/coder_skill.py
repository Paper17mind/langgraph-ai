import os
import subprocess
from langchain.tools import tool

@tool
def write_code_to_file(filename: str, content: str) -> str:
    """
    Creates or overwrites a file with the provided code or text content.
    Returns a success message or an error if it fails (e.g. syntax errors).
    """
    try:
        abs_path = os.path.abspath(filename)
        dir_name = os.path.dirname(abs_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        # Optional: Try to run python -m py_compile to check syntax if it's a python file
        if filename.endswith(".py"):
            try:
                subprocess.run(f"python -m py_compile {filename}", shell=True, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                return f"File saved, but there is a Syntax Error:\n{e.stderr.strip()}"

        return f"Successfully wrote {len(content.splitlines())} lines to {filename}."
    except Exception as e:
        return f"Failed to write file: {e}"
