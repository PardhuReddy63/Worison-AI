import sqlite3
import os
import shutil
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "backend", "app.db")
BACKUP_DIR = os.path.join(PROJECT_ROOT, "backups")

os.makedirs(BACKUP_DIR, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute("""
    PRAGMA table_info(conversations)
    """)
    cols = [row["name"] for row in cur.fetchall()]
    if "session_id" not in cols:
        cur.execute("ALTER TABLE conversations ADD COLUMN session_id TEXT")

    conn.commit()
    conn.close()


def backup_database():
    if not os.path.exists(DB_PATH):
        return
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    shutil.copy(DB_PATH, os.path.join(BACKUP_DIR, f"backup_{ts}.db"))
