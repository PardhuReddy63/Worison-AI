from datetime import datetime
from database import get_db, backup_database


def save_message(user_id: str, role: str, content: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO conversations (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (user_id, role, content, datetime.utcnow().isoformat())
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


def periodic_backup(count: int):
    if count % 20 == 0:
        backup_database()
