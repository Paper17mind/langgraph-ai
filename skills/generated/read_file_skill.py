from langchain_core.tools import tool
import os

@tool
def read_file_content(filepath: str) -> str:
    """Reads the content of a file."""
    try:
        
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        return str(e)
