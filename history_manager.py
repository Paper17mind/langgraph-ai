import sqlite3
import os

MEMORY_STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_store")
os.makedirs(MEMORY_STORE_DIR, exist_ok=True)
DB_PATH = os.path.join(MEMORY_STORE_DIR, "history.db")

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
    return [{"role": row[0], "content": row[1]} for row in rows]

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

# Initialize database on import
init_db()
