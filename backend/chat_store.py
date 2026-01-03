from datetime import datetime
import uuid
from database import get_db


def save_message(user_id: str, role: str, content: str, session_id: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO conversations (user_id, role, content, created_at, session_id) VALUES (?, ?, ?, ?, ?)",
        (user_id, role, content, datetime.utcnow().isoformat(), session_id)
    )
    conn.commit()
    conn.close()


def load_conversation(user_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM conversations WHERE user_id=? ORDER BY id",
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def create_session(user_id: str, title: str) -> str:
    session_id = uuid.uuid4().hex
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_sessions VALUES (?, ?, ?, ?)",

        (session_id, user_id, title, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return session_id


def list_sessions(user_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title FROM chat_sessions WHERE user_id=? ORDER BY created_at DESC",
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [{"id": r["id"], "title": r["title"]} for r in rows]


def load_session_messages(user_id: str, session_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM conversations WHERE user_id=? AND session_id=? ORDER BY id",
        (user_id, session_id)
    )
    rows = cur.fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]
