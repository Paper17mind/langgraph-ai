import subprocess
from langchain.tools import tool

@tool
def execute_system_command(command: str) -> str:
    """
    Executes a bash/system command on the local machine and returns the output or error.
    Use this to run terminal commands (e.g., ls, df, curl, etc.).
    IMPORTANT: If using curl with URLs containing '&', you MUST wrap the URL in quotes!
    """
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True, timeout=10)
        output = result.stdout.strip()
        if not output:
            output = "Command executed successfully with no output."
        
        # Truncate output if it is too long to prevent LLM context limit errors (Error 413)
        if len(output) > 2000:
            return output[:2000] + "\n\n... [OUTPUT TRUNCATED DUE TO LENGTH: The output was over 2000 characters. If you need to see the full output, please re-run the command and redirect it to a file using '> output.txt' and then read the file.]"
            
        return output
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 10 seconds."
    except Exception as e:
        return f"Error executing command: {e}"
