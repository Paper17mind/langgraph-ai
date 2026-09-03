import json
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi
from langchain_core.tools import tool

@tool
def get_youtube_transcript(url: str = "", video_url: str = "") -> str:
    """
    Fetch transcript for a YouTube video.
    Returns the plain spoken text of the video, ready for summarization.
    Also saves the full raw JSON transcript to logs/ for reference.
    Args:
        url: YouTube video URL
        video_url: Alias for url (either parameter works)
    """
    url = url or video_url
    if not url:
        return "Error: URL parameter is required. Please provide 'url' or 'video_url'."
    parsed = urlparse(url)
    video_id = None
    if parsed.hostname in ("youtu.be",):
        video_id = parsed.path.lstrip('/')
    elif parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            video_id = qs.get('v', [None])[0]
        elif parsed.path.startswith('/embed/'):
            video_id = parsed.path.split('/')[2]
        elif parsed.path.startswith('/shorts/'):
            video_id = parsed.path.split('/')[2]
    if not video_id:
        raise ValueError("Could not extract video ID from the provided URL")

    try:
        t_list = YouTubeTranscriptApi().list(video_id)
        transcript = t_list.find_transcript(["en", "id"])
        snippets = transcript.fetch()
        transcript_entries = [
            {"text": s.text, "start": s.start, "duration": s.duration}
            for s in snippets
        ]
    except Exception as e:
        raise ValueError(f"Failed to fetch transcript: {e}")

    # Save raw JSON to log file for reference
    log_dir = os.path.join("logs", "get_youtube_transcript")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(log_dir, f"{timestamp}.txt")
    raw_json = json.dumps(transcript_entries, ensure_ascii=False, indent=2)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(raw_json)

    # Extract plain spoken text (no timestamps, no JSON structure)
    plain_text = " ".join(
        entry["text"].strip() for entry in transcript_entries if entry["text"].strip()
    )

    # Calculate duration
    total_duration_sec = 0
    if transcript_entries:
        last = transcript_entries[-1]
        total_duration_sec = last["start"] + last.get("duration", 0)
    minutes = int(total_duration_sec // 60)
    seconds = int(total_duration_sec % 60)

    return (
        f"✅ Transkrip video berhasil diambil.\n"
        f"Video ID: {video_id}\n"
        f"Durasi: {minutes}m {seconds}s\n"
        f"Jumlah segmen: {len(transcript_entries)}\n"
        f"Raw JSON disimpan ke: {log_path}\n\n"
        f"--- TRANSKRIP LENGKAP ---\n{plain_text}"
    )

__all__ = ["get_youtube_transcript"]
