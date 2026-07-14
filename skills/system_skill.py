import subprocess
from llm_client import llm

def execute(user_message: str, session_id: str = "default") -> str:
    """
    Translates the user's request into a bash command, executes it, and returns the result.
    """
    system_prompt = """You are a Linux command generator. 
The user will ask you to perform a system task. 
Your ONLY job is to output the EXACT terminal command to run. 
Do NOT wrap the command in markdown, backticks, or any explanation. 
Just the raw bash command."""

    command = llm.ask(prompt=user_message, system_prompt=system_prompt)
    
    # Very basic safety check to prevent accidental destructive commands if needed
    # (Though we rely on Telegram whitelisting for security)
    
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True, timeout=10)
        output = result.stdout.strip()
        if not output:
            output = "Command executed successfully with no output."
            
        return f"Ran command: `{command}`\n\nOutput:\n```\n{output}\n```"
    except subprocess.CalledProcessError as e:
        return f"Failed to run: `{command}`\n\nError:\n```\n{e.stderr.strip()}\n```"
    except subprocess.TimeoutExpired:
        return f"Command `{command}` timed out."
    except Exception as e:
        return f"Error executing system command: {e}"
