import uuid
import bcrypt
import re
from datetime import datetime
from typing import Optional, Tuple
from database import get_db


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def validate_password(password: str) -> Tuple[bool, str]:
    if len(password) < 8:
        return False, "Minimum 8 characters required"
    if not re.search(r"[A-Z]", password):
        return False, "Add at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Add at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Add at least one number"
    if not re.search(r"[@$!%*?&]", password):
        return False, "Add at least one special character"
    return True, ""


def register_user(email: str, password: str) -> Optional[str]:
    user_id = uuid.uuid4().hex
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            (user_id, email, hash_password(password), datetime.utcnow().isoformat())
        )
        conn.commit()
        return user_id
    except Exception:
        return None
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Optional[str]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, password FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None
    if not bcrypt.checkpw(
        password.encode("utf-8"),
        row["password"].encode("utf-8")
    ):
        return None
    return row["id"]
