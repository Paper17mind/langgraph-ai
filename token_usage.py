import json
with open('logs/token_usage.jsonl', 'r') as f:
    for line in f:
        data = json.loads(line)
        print(data)