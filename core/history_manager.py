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
