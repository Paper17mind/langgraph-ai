import sqlite3
import os
import time

MEMORY_STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "memory_store")
os.makedirs(MEMORY_STORE_DIR, exist_ok=True)
DB_PATH = os.path.join(MEMORY_STORE_DIR, "history.db")

def init_scheduler_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            task TEXT,
            run_at INTEGER,
            status TEXT DEFAULT 'pending'
        )
    ''')
    conn.commit()
    conn.close()

def add_schedule(session_id: str, task: str, delay_seconds: int):
    run_at = int(time.time()) + delay_seconds
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO schedules (session_id, task, run_at)
        VALUES (?, ?, ?)
    ''', (session_id, task, run_at))
    conn.commit()
    conn.close()

def get_pending_schedules():
    current_time = int(time.time())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, session_id, task FROM schedules 
        WHERE status = 'pending' AND run_at <= ?
    ''', (current_time,))
    rows = cursor.fetchall()
    conn.close()
    
    return [{"id": row[0], "session_id": row[1], "task": row[2]} for row in rows]

def mark_schedule_done(schedule_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE schedules SET status = 'done' WHERE id = ?
    ''', (schedule_id,))
    conn.commit()
    conn.close()

init_scheduler_db()
