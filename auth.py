"""Auth helpers: bcrypt password hashing + DB-backed sessions.

Sessions are random opaque tokens stored server-side in the user_sessions
table. The cookie only carries the session id (no signing needed since the
id itself is already random and validated against the DB).
"""
from __future__ import annotations

import secrets
import time
from typing import Optional

from passlib.context import CryptContext

import database as db

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd.verify(password, hashed)
    except Exception:
        return False


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def create_session(user_id: int, lifetime_seconds: int) -> str:
    sid = new_session_id()
    db.create_session(sid, user_id, int(time.time()) + lifetime_seconds)
    return sid


def user_from_session(session_id: Optional[str]) -> Optional[dict]:
    if not session_id:
        return None
    return db.get_user_by_session(session_id)


def revoke_session(session_id: Optional[str]) -> None:
    if session_id:
        db.delete_session(session_id)
