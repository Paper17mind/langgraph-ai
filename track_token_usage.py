#!/usr/bin/env python3
"""Token Usage Tracker Script - Baca logs/token_usage.jsonl & output stats per request/response"""


def read_token_logs(logs_path):
    """Baca file JSONL dan parse data token usage."""
    requests = []
    
    with open(logs_path, 'r') as f:
        for line in f:
            if not line.strip():  # Skip empty lines
                continue
            
            try:
                entry = json.loads(line)
                
                # Extract fields (handle both single and nested structure)
                request_data = {}
                
                # Try to find all top-level keys that represent token counts
                for key in ['completion_tokens', 'prompt_tokens']:
                    if isinstance(entry, dict):
                        val = entry.get(key)
                        if val is not None:
                            request_data[key] = int(val)
                    
                    elif isinstance(value := entry.get('token_usage'), dict):
                        completion_val = value.get('completion_tokens')
                        prompt_val = value.get('prompt_tokens')
                        if completion_val and prompt_val:
                            request_data['total'] = (int(completion_val) + int(prompt_val))
                            
                requests.append(request_data)
            except json.JSONDecodeError as e:
                print(f"❌ Error parsing JSON on line {line.strip()}: {e}")
    
    return requests


def analyze_requests(requests):
    """Analisis dan output statistics dari semua request."""
    
    total_tokens = 0
    completion_count = 0
    prompt_count = 0
    
    for req in requests:
        if isinstance(req, dict) and 'completion_tokens' in req:
            completion_count += int(req['completion_tokens'])
            total_tokens += int(req.get('total', req.get('prompt_tokens')))
        
        if isinstance(req, dict) and 'prompt_tokens' in req:
            prompt_count += 1
    
    return {
        'requests': len(requests),
        'total_completion_tokens': completion_count,
        'total_prompt_tokens': prompt_count,
        'total_total_tokens': total_tokens,
        'avg_completion_per_request': round(completion_count / requests[0]['completion_tokens'] if requests else 0, 2) if requests else None,
    }


def format_output(stats):
    """Format output dalam bentuk yang mudah dibaca."""
    
    lines = []
    lines.append("=" * 60)
    lines.append("📊 TOKEN USAGE ANALYSIS REPORT")
    lines.append("=" * 60)
    lines.append("")
    
    # Summary section
    lines.append(f"Total Requests: {stats['requests']}")
    lines.append("-" * 40)
    lines.append(f"Completion Tokens (Output):   {stats['total_completion_tokens']:,}")
    lines.append(f"Prompt Tokens (Input):        {stats['total_prompt_tokens']:,}")
    lines.append(f"Total Combined Tokens:        {stats['total_total_tokens']:>12,}")
    
    if stats['avg_completion_per_request']:
        lines.append("")
        lines.append("Average per Request:")
        lines.append("-" * 40)
        lines.append(f"{stats['avg_completion_per_request']:.2f} completion tokens")
    
    # Breakdown by token type (if available in data)
    if 'audio_tokens' not in stats:
        audio_count = sum(1 for r in requests if isinstance(r, dict) and r.get('audio_tokens') is not None)
        reasoning_count = sum(1 for r in requests if isinstance(r, dict) and r.get('reasoning_tokens') is not None)
        
        lines.append("")
        lines.append("🔍 Token Type Breakdown:")
        lines.append("-" * 40)
        if audio_count > 0:
            lines.append(f"- Audio Tokens: {audio_count:,}")
        else:
            lines.append("- No audio tokens detected")
        
        if reasoning_count > 0:
            lines.append(f"- Reasoning Tokens: {reasoning_count:,}")
        else:
            lines.append("- No reasoning tokens detected")
    
    # Detailed per-request breakdown (limit to first 10 for readability)
    detailed = []
    total_detail_tokens = sum(int(r.get('completion_tokens', r.get('prompt_tokens')) or 0) 
                               if isinstance(r, dict) else 0 
                               for r in requests[:5])
    
    lines.append("")
    lines.append(f"📝 Per-Request Breakdown (First {len(requests)}):")
    lines.append("-" * 40)
    
    # Show first request details if available
    if stats['requests'] > 1:
        req_data = requests[stats['requests'] - 2]
        completion_tokens = int(req_data.get('completion_tokens', 'N/A')) or "N/A"
        prompt_tokens = int(req_data.get('prompt_tokens', 'N/A')) or "N/A"
        
        lines.append(f"\nRequest {len(requests):>3}:")
        lines.append("-" * 40)
        lines.append(f"- Completion Tokens:   {completion_tokens:>12,}")
        lines.append(f"- Prompt Tokens:       {prompt_tokens:>12,}")
    
    if total_detail_tokens > 0 and len(requests) >= 3:
        req_data = requests[stats['requests'] - 4]
        completion_tokens = int(req_data.get('completion_tokens', 'N/A')) or "N/A"
        prompt_tokens = int(req_data.get('prompt_tokens', 'N/A')) or "N/A"
        
        lines.append(f"\nRequest {len(requests):>3}:")
        lines.append("-" * 40)
        lines.append(f"- Completion Tokens:   {completion_tokens:>12,}")
        lines.append(f"- Prompt Tokens:       {prompt_tokens:>12,}")
    
    # Footer with key metrics
    if stats['requests'] > 0 and stats['total_completion_tokens'] > 0:
        completion_rate = (stats['total_completion_tokens'] / 
                         sum(int(r.get('completion_tokens', r.get('prompt_tokens')) or 0) for r in requests)) * 100
        
        lines.append("")
        lines.append("=" * 60)
        lines.append("🎯 KEY METRICS")
        lines.append("=" * 60)
        lines.append(f"Completion Rate: {completion_rate:.2f}% of total tokens are output completion")
    
    return "\n".join(lines)


def main():
    logs_path = "logs/token_usage.jsonl"
    
    if not os.path.exists(logs_path):
        print(f"❌ Error: File '{logs_path}' tidak ditemukan!")
        exit(1)
    
    # Baca dan parse data
    requests = read_token_logs(logs_path)
    
    if len(requests) == 0 or all(not r.get('completion_tokens') for r in requests):
        print("⚠️ Warning: Tidak ada data token yang valid ditemukan!")
        return
    
    # Analisis & output
    stats = analyze_requests(requests)
    report = format_output(stats)
    
    print(report)


if __name__ == "__main__":
    main()
