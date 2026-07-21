import sqlite3
import os
import re

MEMORY_STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "memory_store")
os.makedirs(MEMORY_STORE_DIR, exist_ok=True)
DB_PATH = os.path.join(MEMORY_STORE_DIR, "history.db")

MAX_CONTENT_CHARS = 500  # max chars per history message before truncating

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_message(session_id: str, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (session_id, role, content)
        VALUES (?, ?, ?)
    ''', (session_id, role, content))
    conn.commit()
    conn.close()

def _trim_content(content: str) -> str:
    """
    Trim long content to reduce tokens when re-sending history to LLM.
    Especially useful for tool outputs containing HTML, JSON, or long code.
    Original content is preserved in DB — trimming only happens at read time.
    """
    if not content or len(content) <= MAX_CONTENT_CHARS:
        return content

    # Collapse code blocks that are too long
    content = re.sub(
        r'```[\s\S]{200,}?```',
        '[... kode panjang dipotong ...]',
        content
    )

    # After collapsing code blocks, check again
    if len(content) <= MAX_CONTENT_CHARS:
        return content

    # Detect HTML-heavy content
    if re.search(r'<[a-zA-Z][^>]{0,50}>', content):
        return content[:MAX_CONTENT_CHARS] + f'\n[... +{len(content)-MAX_CONTENT_CHARS} chars HTML dipotong ...]'

    # Detect JSON-like content
    stripped = content.strip()
    if stripped.startswith('{') or stripped.startswith('['):
        return content[:MAX_CONTENT_CHARS] + f'\n[... +{len(content)-MAX_CONTENT_CHARS} chars JSON dipotong ...]'

    # Generic long content
    return content[:MAX_CONTENT_CHARS] + f'\n[... +{len(content)-MAX_CONTENT_CHARS} chars dipotong ...]'

def get_history(session_id: str, limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT role, content FROM (
            SELECT role, content, timestamp FROM messages 
            WHERE session_id = ? 
            ORDER BY timestamp DESC LIMIT ?
        ) ORDER BY timestamp ASC
    ''', (session_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": row[0], "content": _trim_content(row[1])} for row in rows]


def get_smart_history(session_id: str, recent_count: int = 4, older_count: int = 10):
    """
    Token-efficient history retrieval:
    - `recent_count` most recent messages: returned full (trimmed by _trim_content)
    - Up to `older_count` messages before that: compressed into a single summary block
    
    This avoids sending 20 full messages every turn. Older messages are summarized
    as "User: <first 80 chars>..." to preserve topic awareness without full content.
    """
    total = recent_count + older_count
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT role, content FROM (
            SELECT role, content, timestamp FROM messages 
            WHERE session_id = ? 
            ORDER BY timestamp DESC LIMIT ?
        ) ORDER BY timestamp ASC
    ''', (session_id, total))
    rows = cursor.fetchall()
    conn.close()

    if len(rows) <= recent_count:
        # Not enough messages to need summarization
        return [{"role": row[0], "content": _trim_content(row[1])} for row in rows]

    # Split: older messages get compressed, recent stay full
    split_point = len(rows) - recent_count
    older = rows[:split_point]
    recent = rows[split_point:]

    # Compress older messages into a single summary
    summary_lines = []
    for role, content in older:
        label = "User" if role == "user" else "AI"
        short = (content or "")[:80].replace("\n", " ").strip()
        if len(content or "") > 80:
            short += "..."
        summary_lines.append(f"- {label}: {short}")

    summary_block = "[Ringkasan percakapan sebelumnya]\n" + "\n".join(summary_lines)

    result = [{"role": "system", "content": summary_block}]
    for role, content in recent:
        result.append({"role": role, "content": _trim_content(content)})

    return result

def get_all_sessions(prefix: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT session_id FROM messages WHERE session_id LIKE ?
    ''', (prefix + '%',))
    rows = cursor.fetchall()
    conn.close()
    
    sessions = []
    for row in rows:
        session_id = row[0]
        # Remove prefix
        if session_id.startswith(prefix):
            sessions.append(session_id[len(prefix):])
    return sessions

def clear_history(session_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()

# Initialize database on import
init_db()
