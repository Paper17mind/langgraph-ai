import os
import json
import datetime

def log_request(model: str, prompt: str, response: str):
    """
    Logs the user interaction to logs/requests.jsonl
    """
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
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
