import json
from typing import List, Dict

def read_jsonl(filepath: str) -> List[Dict]:
    """Read .jsonl file, return list of JSON objects.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []
