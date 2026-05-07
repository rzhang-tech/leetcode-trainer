"""SQLite layer with multi-user support.

Every domain table (problems, quiz_cards) carries a user_id. Every CRUD
function takes user_id and enforces it in WHERE clauses. The middleware in
main.py is responsible for resolving the current user from the session
cookie before calling any of these.
"""
from __future__ import annotations

import datetime
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from config import DATABASE_PATH, DEFAULT_EASE, DEFAULT_INTERVALS

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash   TEXT    NOT NULL,
    is_admin        INTEGER NOT NULL DEFAULT 0,
    daily_ai_calls  INTEGER NOT NULL DEFAULT 0,
    ai_quota_day    TEXT    NOT NULL DEFAULT '',
    created_at      INTEGER NOT NULL,
    last_login_at   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS user_sessions (
    id          TEXT    PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL,
    created_at  INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user    ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);

CREATE TABLE IF NOT EXISTS problems (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL DEFAULT 0,
    lc_number       INTEGER NOT NULL,
    title           TEXT    NOT NULL,
    difficulty      TEXT    NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
    tags            TEXT    NOT NULL DEFAULT '[]',
    first_solved_at INTEGER NOT NULL,
    notes           TEXT    NOT NULL DEFAULT '',
    ai_summary      TEXT    NOT NULL DEFAULT '',
    approach_clear  INTEGER NOT NULL DEFAULT 1,
    approach_desc   TEXT    NOT NULL DEFAULT '',
    syntax_errors   TEXT    NOT NULL DEFAULT '',
    style_issues    TEXT    NOT NULL DEFAULT '',
    private_notes   TEXT    NOT NULL DEFAULT '',  -- never fed to the AI
    review_count    INTEGER NOT NULL DEFAULT 0,
    review_step     INTEGER NOT NULL DEFAULT 0,
    next_review_at  INTEGER NOT NULL,
    ease_factor     REAL    NOT NULL DEFAULT 2.5,
    last_reviewed_at INTEGER,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);

-- idx_problems_user_lc and idx_problems_user_due are created in init_db()
-- after the user_id column has been added (matters for upgrades).

CREATE TABLE IF NOT EXISTS review_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id    INTEGER NOT NULL,
    quiz_card_id  INTEGER,
    status        TEXT    NOT NULL,
    reviewed_at   INTEGER NOT NULL,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE,
    FOREIGN KEY (quiz_card_id) REFERENCES quiz_cards(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_review_logs_problem ON review_logs(problem_id);
CREATE INDEX IF NOT EXISTS idx_review_logs_time    ON review_logs(reviewed_at);

CREATE TABLE IF NOT EXISTS quiz_cards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL DEFAULT 0,
    problem_id      INTEGER NOT NULL,
    question        TEXT    NOT NULL,
    hint            TEXT,
    answer          TEXT,
    category        TEXT,
    review_count    INTEGER NOT NULL DEFAULT 0,
    review_step     INTEGER NOT NULL DEFAULT 0,
    next_review_at  INTEGER NOT NULL,
    ease_factor     REAL    NOT NULL DEFAULT 2.5,
    last_reviewed_at INTEGER,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

-- idx_quiz_cards_user_problem and idx_quiz_cards_user_due are created in
-- init_db() after the user_id column has been added.

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as c:
        c.executescript(SCHEMA)

        # Migration 1: review_logs.quiz_card_id (added in card-level review refactor)
        cols = [r[1] for r in c.execute("PRAGMA table_info(review_logs)").fetchall()]
        if "quiz_card_id" not in cols:
            c.execute("ALTER TABLE review_logs ADD COLUMN quiz_card_id INTEGER")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_review_logs_card "
            "ON review_logs(quiz_card_id)"
        )

        # Migration 2: structured note fields on problems
        prob_cols = [r[1] for r in c.execute("PRAGMA table_info(problems)").fetchall()]
        for col, decl in (
            ("approach_clear", "INTEGER NOT NULL DEFAULT 1"),
            ("approach_desc",  "TEXT NOT NULL DEFAULT ''"),
            ("syntax_errors",  "TEXT NOT NULL DEFAULT ''"),
            ("style_issues",   "TEXT NOT NULL DEFAULT ''"),
            ("private_notes",  "TEXT NOT NULL DEFAULT ''"),
        ):
            if col not in prob_cols:
                c.execute(f"ALTER TABLE problems ADD COLUMN {col} {decl}")

        # Migration 3: user_id on problems & quiz_cards (multi-user refactor).
        # Existing rows default to user_id=0 (orphan); the first /register call
        # adopts them.
        prob_cols = [r[1] for r in c.execute("PRAGMA table_info(problems)").fetchall()]
        if "user_id" not in prob_cols:
            c.execute("ALTER TABLE problems ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        card_cols = [r[1] for r in c.execute("PRAGMA table_info(quiz_cards)").fetchall()]
        if "user_id" not in card_cols:
            c.execute("ALTER TABLE quiz_cards ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")

        # Now safe to create indexes that reference the (possibly new) user_id column.
        c.execute("CREATE INDEX IF NOT EXISTS idx_problems_user_lc      ON problems(user_id, lc_number)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_problems_user_due     ON problems(user_id, next_review_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_quiz_cards_user_problem ON quiz_cards(user_id, problem_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_quiz_cards_user_due     ON quiz_cards(user_id, next_review_at)")

        # The unique constraint on lc_number became (user_id, lc_number). We
        # can't drop the old UNIQUE on a vanilla SQLite ALTER. The new compound
        # index above covers lookups; uniqueness is enforced at app-level via
        # get_problem_by_lc + per-user check before insert.

        if c.execute("SELECT COUNT(*) FROM settings WHERE key='intervals'").fetchone()[0] == 0:
            c.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ("intervals", json.dumps(DEFAULT_INTERVALS)),
            )


# ---------- helpers ----------
def _row_to_problem(row: sqlite3.Row) -> dict:
    p = dict(row)
    p["tags"] = json.loads(p["tags"] or "[]")
    if "approach_clear" in p:
        p["approach_clear"] = bool(p["approach_clear"])
    if p["ai_summary"]:
        try:
            p["ai_summary"] = json.loads(p["ai_summary"])
        except Exception:
            pass
    return p


def _row_to_user(row: sqlite3.Row) -> dict:
    u = dict(row)
    u["is_admin"] = bool(u["is_admin"])
    return u


# =====================================================================
# Users
# =====================================================================
def count_users() -> int:
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def get_user_by_id(uid: int) -> Optional[dict]:
    with get_conn() as c:
        r = c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return _row_to_user(r) if r else None


def get_user_by_email(email: str) -> Optional[dict]:
    with get_conn() as c:
        r = c.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return _row_to_user(r) if r else None


def create_user(email: str, password_hash: str, is_admin: bool = False) -> dict:
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO users (email, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)",
            (email, password_hash, 1 if is_admin else 0, now),
        )
        uid = cur.lastrowid
        r = c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return _row_to_user(r)


def update_last_login(user_id: int) -> None:
    with get_conn() as c:
        c.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (int(time.time()), user_id))


def adopt_orphan_data(user_id: int) -> int:
    """Attribute every row whose user_id == 0 to this user. Returns number of rows updated.
    Called once when the very first user registers, so they pick up any data
    that existed before the multi-user migration."""
    with get_conn() as c:
        n1 = c.execute("UPDATE problems  SET user_id = ? WHERE user_id = 0", (user_id,)).rowcount
        n2 = c.execute("UPDATE quiz_cards SET user_id = ? WHERE user_id = 0", (user_id,)).rowcount
    return (n1 or 0) + (n2 or 0)


# AI quota: lazy reset on access. We compare the stored UTC date string with
# today's, reset to 0 if different, then increment.
def check_and_consume_ai_quota(user_id: int, daily_limit: int) -> tuple[bool, int]:
    """Returns (allowed, calls_used_today). Atomically resets+increments."""
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    with get_conn() as c:
        r = c.execute(
            "SELECT is_admin, daily_ai_calls, ai_quota_day FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not r:
            return False, 0
        is_admin, calls, day = r["is_admin"], r["daily_ai_calls"], r["ai_quota_day"]
        if day != today:
            calls = 0
        if not is_admin and calls >= daily_limit:
            return False, calls
        c.execute(
            "UPDATE users SET daily_ai_calls = ?, ai_quota_day = ? WHERE id = ?",
            (calls + 1, today, user_id),
        )
    return True, calls + 1


# =====================================================================
# Sessions
# =====================================================================
def create_session(session_id: str, user_id: int, expires_at: int) -> None:
    with get_conn() as c:
        c.execute(
            "INSERT INTO user_sessions (id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, expires_at, int(time.time())),
        )


def get_user_by_session(session_id: str) -> Optional[dict]:
    now = int(time.time())
    with get_conn() as c:
        r = c.execute(
            """SELECT u.* FROM user_sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.id = ? AND s.expires_at > ?""",
            (session_id, now),
        ).fetchone()
    return _row_to_user(r) if r else None


def delete_session(session_id: str) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM user_sessions WHERE id = ?", (session_id,))


def cleanup_expired_sessions() -> int:
    with get_conn() as c:
        cur = c.execute("DELETE FROM user_sessions WHERE expires_at < ?", (int(time.time()),))
        return cur.rowcount or 0


# =====================================================================
# Problems (all scoped to user_id)
# =====================================================================
def get_problem(pid: int, user_id: int) -> Optional[dict]:
    with get_conn() as c:
        r = c.execute(
            "SELECT * FROM problems WHERE id = ? AND user_id = ?",
            (pid, user_id),
        ).fetchone()
    return _row_to_problem(r) if r else None


def get_problem_by_lc(lc_number: int, user_id: int) -> Optional[dict]:
    with get_conn() as c:
        r = c.execute(
            "SELECT * FROM problems WHERE lc_number = ? AND user_id = ?",
            (lc_number, user_id),
        ).fetchone()
    return _row_to_problem(r) if r else None


def create_problem(data: dict, user_id: int) -> dict:
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO problems
               (user_id, lc_number, title, difficulty, tags, first_solved_at,
                notes, ai_summary,
                approach_clear, approach_desc, syntax_errors, style_issues, private_notes,
                review_count, review_step, next_review_at, ease_factor,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?,
                       ?, ?,
                       ?, ?, ?, ?, ?,
                       0, 0, ?, ?,
                       ?, ?)""",
            (
                user_id,
                data["lc_number"],
                data["title"],
                data["difficulty"],
                json.dumps(data.get("tags") or []),
                data.get("first_solved_at") or now,
                data.get("notes", ""),
                "",
                1 if data.get("approach_clear", True) else 0,
                data.get("approach_desc", ""),
                data.get("syntax_errors", ""),
                data.get("style_issues", ""),
                data.get("private_notes", ""),
                data.get("next_review_at", now + 86400),
                data.get("ease_factor", DEFAULT_EASE),
                now,
                now,
            ),
        )
        pid = cur.lastrowid
        r = c.execute("SELECT * FROM problems WHERE id = ?", (pid,)).fetchone()
    return _row_to_problem(r)


def update_problem(pid: int, user_id: int, data: dict) -> Optional[dict]:
    fields: list[str] = []
    values: list[Any] = []
    for k in (
        "title", "difficulty", "notes", "first_solved_at",
        "approach_desc", "syntax_errors", "style_issues", "private_notes",
    ):
        if k in data and data[k] is not None:
            fields.append(f"{k} = ?")
            values.append(data[k])
    if "approach_clear" in data and data["approach_clear"] is not None:
        fields.append("approach_clear = ?")
        values.append(1 if data["approach_clear"] else 0)
    if data.get("tags") is not None:
        fields.append("tags = ?")
        values.append(json.dumps(data["tags"]))
    if data.get("ai_summary") is not None:
        v = data["ai_summary"]
        fields.append("ai_summary = ?")
        values.append(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    if not fields:
        return get_problem(pid, user_id)
    fields.append("updated_at = ?")
    values.append(int(time.time()))
    values.extend([pid, user_id])
    with get_conn() as c:
        c.execute(
            f"UPDATE problems SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
    return get_problem(pid, user_id)


def delete_problem(pid: int, user_id: int) -> bool:
    with get_conn() as c:
        cur = c.execute(
            "DELETE FROM problems WHERE id = ? AND user_id = ?", (pid, user_id)
        )
        return cur.rowcount > 0


def list_problems(
    user_id: int,
    *,
    difficulty: Optional[str] = None,
    tag: Optional[str] = None,
    sort: str = "lc_number",
    order: str = "asc",
) -> list[dict]:
    sort_map = {
        "lc_number": "lc_number",
        "first_solved_at": "first_solved_at",
        "next_review_at": "next_review_at",
        "review_count": "review_count",
        "difficulty": "difficulty",
        "updated_at": "updated_at",
    }
    sort_col = sort_map.get(sort, "lc_number")
    order_sql = "DESC" if str(order).lower() == "desc" else "ASC"

    sql = "SELECT * FROM problems WHERE user_id = ?"
    args: list[Any] = [user_id]
    if difficulty:
        sql += " AND difficulty = ?"
        args.append(difficulty)
    sql += f" ORDER BY {sort_col} {order_sql}"

    with get_conn() as c:
        rows = c.execute(sql, args).fetchall()
    out = [_row_to_problem(r) for r in rows]
    if tag:
        out = [p for p in out if tag in p["tags"]]
    return out


# =====================================================================
# Today / calendar / review groups (all per-user)
# =====================================================================
def list_due_groups(user_id: int, now_ts: Optional[int] = None) -> list[dict]:
    now_ts = now_ts or int(time.time())
    today = datetime.datetime.fromtimestamp(now_ts)
    today_end = int(today.replace(hour=23, minute=59, second=59).timestamp())
    out: list[dict] = []
    with get_conn() as c:
        problems = c.execute(
            "SELECT * FROM problems WHERE user_id = ? ORDER BY lc_number",
            (user_id,),
        ).fetchall()
        for prow in problems:
            p = _row_to_problem(prow)
            total = c.execute(
                "SELECT COUNT(*) FROM quiz_cards WHERE problem_id = ? AND user_id = ?",
                (p["id"], user_id),
            ).fetchone()[0]
            due_rows = c.execute(
                "SELECT * FROM quiz_cards WHERE problem_id = ? AND user_id = ? "
                "AND next_review_at <= ? ORDER BY next_review_at",
                (p["id"], user_id, today_end),
            ).fetchall()
            if total == 0:
                out.append({
                    "problem": _problem_brief(p),
                    "due_cards": [],
                    "due_count": 0,
                    "needs_generation": True,
                })
            elif due_rows:
                out.append({
                    "problem": _problem_brief(p),
                    "due_cards": [dict(r) for r in due_rows],
                    "due_count": len(due_rows),
                    "needs_generation": False,
                })
    return out


def _problem_brief(p: dict) -> dict:
    return {
        "id": p["id"],
        "lc_number": p["lc_number"],
        "title": p["title"],
        "difficulty": p["difficulty"],
        "tags": p["tags"],
    }


def list_cards_due_in_range(user_id: int, start_ts: int, end_ts: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            """SELECT qc.*, p.lc_number, p.title, p.difficulty
               FROM quiz_cards qc JOIN problems p ON p.id = qc.problem_id
               WHERE qc.user_id = ? AND qc.next_review_at >= ? AND qc.next_review_at <= ?
               ORDER BY qc.next_review_at""",
            (user_id, start_ts, end_ts),
        ).fetchall()
    return [dict(r) for r in rows]


# =====================================================================
# Quiz cards (per-user)
# =====================================================================
def get_card(cid: int, user_id: int) -> Optional[dict]:
    with get_conn() as c:
        r = c.execute(
            "SELECT * FROM quiz_cards WHERE id = ? AND user_id = ?",
            (cid, user_id),
        ).fetchone()
    return dict(r) if r else None


def list_cards_by_problem(pid: int, user_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM quiz_cards WHERE problem_id = ? AND user_id = ? "
            "ORDER BY next_review_at, id",
            (pid, user_id),
        ).fetchall()
    return [dict(r) for r in rows]


def create_card(data: dict, user_id: int) -> dict:
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO quiz_cards
               (user_id, problem_id, question, hint, answer, category,
                review_count, review_step, next_review_at, ease_factor,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)""",
            (
                user_id,
                data["problem_id"],
                data["question"],
                data.get("hint"),
                data.get("answer"),
                data.get("category"),
                data["next_review_at"],
                data.get("ease_factor", DEFAULT_EASE),
                now,
                now,
            ),
        )
        cid = cur.lastrowid
        r = c.execute("SELECT * FROM quiz_cards WHERE id = ?", (cid,)).fetchone()
    return dict(r)


def update_card(cid: int, user_id: int, data: dict) -> Optional[dict]:
    fields: list[str] = []
    values: list[Any] = []
    for k in ("question", "hint", "answer", "category"):
        if k in data and data[k] is not None:
            fields.append(f"{k} = ?")
            values.append(data[k])
    if not fields:
        return get_card(cid, user_id)
    fields.append("updated_at = ?")
    values.append(int(time.time()))
    values.extend([cid, user_id])
    with get_conn() as c:
        c.execute(
            f"UPDATE quiz_cards SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
    return get_card(cid, user_id)


def delete_card(cid: int, user_id: int) -> bool:
    with get_conn() as c:
        cur = c.execute(
            "DELETE FROM quiz_cards WHERE id = ? AND user_id = ?", (cid, user_id)
        )
        return cur.rowcount > 0


def apply_card_review(
    cid: int, user_id: int, *, review_step: int, next_review_at: int, ease_factor: float
) -> None:
    now = int(time.time())
    with get_conn() as c:
        c.execute(
            """UPDATE quiz_cards
               SET review_count = review_count + 1,
                   review_step  = ?,
                   next_review_at = ?,
                   ease_factor  = ?,
                   last_reviewed_at = ?,
                   updated_at   = ?
               WHERE id = ? AND user_id = ?""",
            (review_step, next_review_at, ease_factor, now, now, cid, user_id),
        )


def log_card_review(card_id: int, problem_id: int, status: str) -> None:
    with get_conn() as c:
        c.execute(
            "INSERT INTO review_logs (problem_id, quiz_card_id, status, reviewed_at) "
            "VALUES (?, ?, ?, ?)",
            (problem_id, card_id, status, int(time.time())),
        )


def recent_review_logs(user_id: int, since_ts: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            """SELECT rl.id, rl.problem_id, rl.quiz_card_id, rl.status, rl.reviewed_at,
                      p.lc_number, p.title, p.difficulty, p.tags
               FROM review_logs rl
               JOIN problems p ON p.id = rl.problem_id
               WHERE p.user_id = ? AND rl.reviewed_at >= ?
               ORDER BY rl.reviewed_at DESC""",
            (user_id, since_ts),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"] or "[]")
        out.append(d)
    return out


# =====================================================================
# Settings (global, single-tenant for now)
# =====================================================================
def get_setting(key: str, default: Any = None) -> Any:
    with get_conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not r:
        return default
    try:
        return json.loads(r["value"])
    except Exception:
        return r["value"]


def set_setting(key: str, value: Any) -> None:
    with get_conn() as c:
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
