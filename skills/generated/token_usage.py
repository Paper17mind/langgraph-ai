import json
import os
from datetime import datetime, date
from langchain_core.tools import tool

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs", "token_usage.jsonl")

def _read_records() -> list[dict]:
    """Read all token usage records from jsonl log file."""
    if not os.path.exists(LOG_PATH):
        return []
    records = []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    return records

@tool
def get_token_usage_stats(period: str = "today") -> str:
    """
    Tampilkan statistik penggunaan token LLM dari log file.
    Parameter 'period' bisa: 'today' (hari ini), 'week' (7 hari terakhir), 'all' (semua waktu).
    Menampilkan: total request, total token (prompt + completion), rata-rata per request, dan estimasi biaya.
    Gunakan tool ini ketika user bertanya tentang pemakaian token, biaya API, atau seberapa banyak token terpakai.
    """
    records = _read_records()
    if not records:
        return "❌ Belum ada data token usage. Log file belum ada atau masih kosong."

    today = date.today()
    filtered = []

    for r in records:
        try:
            ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S").date()
        except Exception:
            continue

        if period == "today" and ts == today:
            filtered.append(r)
        elif period == "week" and (today - ts).days <= 7:
            filtered.append(r)
        elif period == "all":
            filtered.append(r)

    if not filtered:
        period_label = {"today": "hari ini", "week": "7 hari terakhir", "all": "semua waktu"}.get(period, period)
        return f"📭 Tidak ada data token usage untuk periode: {period_label}."

    total_prompt = sum(r.get("token_usage", {}).get("prompt_tokens", 0) for r in filtered)
    total_completion = sum(r.get("token_usage", {}).get("completion_tokens", 0) for r in filtered)
    total_reasoning = sum(
        (r.get("token_usage", {}).get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0
        for r in filtered
    )
    total_tokens = total_prompt + total_completion
    n = len(filtered)

    avg_prompt = total_prompt // n if n else 0
    avg_completion = total_completion // n if n else 0
    avg_total = total_tokens // n if n else 0

    # Rough cost estimate (Groq free tier or generic ~$0.27/M input, $0.27/M output)
    cost_usd = (total_prompt * 0.27 + total_completion * 0.27) / 1_000_000

    period_label = {"today": "Hari Ini", "week": "7 Hari Terakhir", "all": "Semua Waktu"}.get(period, period)

    return (
        f"📊 **Statistik Token Usage — {period_label}**\n\n"
        f"• Total request LLM  : {n:,}\n"
        f"• Prompt tokens      : {total_prompt:,}\n"
        f"• Completion tokens  : {total_completion:,}\n"
        f"  └ Reasoning tokens : {total_reasoning:,}\n"
        f"• Total tokens       : {total_tokens:,}\n\n"
        f"📈 **Rata-rata per Request:**\n"
        f"• Prompt avg    : {avg_prompt:,} tokens\n"
        f"• Completion avg: {avg_completion:,} tokens\n"
        f"• Total avg     : {avg_total:,} tokens\n\n"
        f"💸 **Estimasi Biaya:** ~${cost_usd:.4f} USD\n"
        f"   _(asumsi $0.27/M token, cek tarif model aktif untuk akurasi)_"
    )
