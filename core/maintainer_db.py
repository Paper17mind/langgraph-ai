"""
SQLite storage for registered projects, sub-targets, dependencies, and index cache.
"""
import sqlite3
import os
import json
import time
from typing import Dict, Any, List, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "maintainer.db")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_maintainer_db(db_path: Optional[str] = None):
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 1. Projects parent table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            root_path TEXT UNIQUE NOT NULL,
            created_at REAL NOT NULL,
            last_scanned_at REAL
        )
    """)

    # 2. Sub-targets table (nested backend/frontend/microservices)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_subtargets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            rel_path TEXT NOT NULL,
            full_path TEXT NOT NULL,
            ecosystem TEXT NOT NULL, -- php, node, python, go, docker
            manifest_file TEXT,     -- e.g. composer.json, package.json
            runtime_target TEXT,    -- e.g. PHP ^8.1, Node >=18, Python 3.10
            created_at REAL NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, rel_path)
        )
    """)

    # 3. Dependencies table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subtarget_id INTEGER NOT NULL,
            package_name TEXT NOT NULL,
            version_spec TEXT,
            is_dev INTEGER DEFAULT 0,
            FOREIGN KEY (subtarget_id) REFERENCES project_subtargets(id) ON DELETE CASCADE,
            UNIQUE(subtarget_id, package_name)
        )
    """)

    # 4. Code index table (lightweight symbols: file, route, class, function)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS code_symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subtarget_id INTEGER NOT NULL,
            file_rel_path TEXT NOT NULL,
            symbol_type TEXT NOT NULL, -- route, class, function, import
            symbol_name TEXT NOT NULL,
            line_no INTEGER DEFAULT 1,
            FOREIGN KEY (subtarget_id) REFERENCES project_subtargets(id) ON DELETE CASCADE
        )
    """)

    # 5. Vulnerability and bug alerts history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintainer_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            subtarget_id INTEGER,
            alert_type TEXT NOT NULL, -- cve_runtime, cve_dependency, bug_sast
            severity TEXT NOT NULL,   -- CRITICAL, HIGH, MEDIUM, LOW
            title TEXT NOT NULL,
            details TEXT NOT NULL,
            fix_suggestion TEXT,
            status TEXT DEFAULT 'open', -- open, fixed, ignored
            created_at REAL NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


init_maintainer_db()
