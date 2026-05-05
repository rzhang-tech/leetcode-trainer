"""Auth helpers: bcrypt password hashing + DB-backed sessions.

Uses the `bcrypt` package directly rather than passlib — passlib is no longer
maintained and breaks against modern bcrypt releases. Sessions are random
opaque tokens stored server-side in user_sessions; the cookie carries only
the session id (no signing needed since the id itself is already random and
validated against the DB).
"""
from __future__ import annotations

import secrets
import time
from typing import Optional

import bcrypt

import database as db

# bcrypt has a hard 72-byte limit on password input. Truncate at the boundary
# instead of silently failing — for any sane password this is a no-op.
_MAX_PW_BYTES = 72


def _normalize(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_PW_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_normalize(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_normalize(password), hashed.encode("utf-8"))
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
