import os
import json
import datetime

def log_request(model: str, prompt: str, response: str):
    """
    Logs the user interaction to logs/requests.jsonl
    """
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join(log_dir, "requests.jsonl")
    
    log_data = {
        "timestamp": timestamp,
        "model": model,
        "prompt": prompt,
        "response": response
    }
    
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Log Error]: {e}")

def log_internal_step(step_type: str, data: dict):
    """
    Logs internal LLM steps (like tool_call, tool_result) to requests.jsonl
    """
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join(log_dir, "requests.jsonl")
    
    log_data = {
        "timestamp": timestamp,
        "model": "langgraph_internal",
        "type": step_type,
    }
    log_data.update(data)
    
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Log Error]: {e}")

def log_token_usage(usage: dict):
    """
    Logs token usage data to a dedicated lightweight file logs/token_usage.jsonl
    """
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join(log_dir, "token_usage.jsonl")
    
    log_data = {
        "timestamp": timestamp,
        "token_usage": usage
    }
    
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Log Error]: {e}")
