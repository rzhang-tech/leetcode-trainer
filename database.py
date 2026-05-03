"""SQLite layer.

Single-file database, sync calls (FastAPI runs them on its threadpool — fine
for personal-scale usage and avoids the aiosqlite dependency). All JSON-typed
columns (tags, ai_summary) are serialised at the boundary so callers always
see python objects.
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
CREATE TABLE IF NOT EXISTS problems (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lc_number       INTEGER NOT NULL UNIQUE,
    title           TEXT    NOT NULL,
    difficulty      TEXT    NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
    tags            TEXT    NOT NULL DEFAULT '[]',
    first_solved_at INTEGER NOT NULL,
    notes           TEXT    NOT NULL DEFAULT '',         -- legacy / "其他备注"
    ai_summary      TEXT    NOT NULL DEFAULT '',         -- legacy, no longer generated
    approach_clear  INTEGER NOT NULL DEFAULT 1,          -- 1=思路清晰  0=不清晰
    approach_desc   TEXT    NOT NULL DEFAULT '',         -- 当 approach_clear=0 时用户描述的做法
    syntax_errors   TEXT    NOT NULL DEFAULT '',         -- 语法错误 / 语法要点
    style_issues    TEXT    NOT NULL DEFAULT '',         -- 写法优化（不错但可更好）
    review_count    INTEGER NOT NULL DEFAULT 0,
    review_step     INTEGER NOT NULL DEFAULT 0,
    next_review_at  INTEGER NOT NULL,
    ease_factor     REAL    NOT NULL DEFAULT 2.5,
    last_reviewed_at INTEGER,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_problems_next_review ON problems(next_review_at);
CREATE INDEX IF NOT EXISTS idx_problems_lc_number   ON problems(lc_number);

CREATE TABLE IF NOT EXISTS review_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id    INTEGER NOT NULL,
    quiz_card_id  INTEGER,
    status        TEXT    NOT NULL,  -- remembered / fuzzy / forgot
    reviewed_at   INTEGER NOT NULL,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE,
    FOREIGN KEY (quiz_card_id) REFERENCES quiz_cards(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_review_logs_problem ON review_logs(problem_id);
CREATE INDEX IF NOT EXISTS idx_review_logs_time    ON review_logs(reviewed_at);
-- idx_review_logs_card is created in init_db() AFTER the quiz_card_id
-- column has been added (matters for upgrades from older schemas).

CREATE TABLE IF NOT EXISTS quiz_cards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE INDEX IF NOT EXISTS idx_quiz_cards_problem ON quiz_cards(problem_id);
CREATE INDEX IF NOT EXISTS idx_quiz_cards_due     ON quiz_cards(next_review_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # better for concurrent readers
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
        # Migration: review_logs from before card-level tracking lacks quiz_card_id.
        cols = [r[1] for r in c.execute("PRAGMA table_info(review_logs)").fetchall()]
        if "quiz_card_id" not in cols:
            c.execute("ALTER TABLE review_logs ADD COLUMN quiz_card_id INTEGER")
        # Now safe to create the index that depends on the (possibly newly-added) column.
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_review_logs_card "
            "ON review_logs(quiz_card_id)"
        )
        # Migration: structured note fields added in 2nd refactor.
        prob_cols = [r[1] for r in c.execute("PRAGMA table_info(problems)").fetchall()]
        for col, decl in (
            ("approach_clear", "INTEGER NOT NULL DEFAULT 1"),
            ("approach_desc",  "TEXT NOT NULL DEFAULT ''"),
            ("syntax_errors",  "TEXT NOT NULL DEFAULT ''"),
            ("style_issues",   "TEXT NOT NULL DEFAULT ''"),
        ):
            if col not in prob_cols:
                c.execute(f"ALTER TABLE problems ADD COLUMN {col} {decl}")
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
            # leave as raw string if it isn't valid JSON
            pass
    return p


# ---------- problems CRUD ----------
def get_problem(pid: int) -> Optional[dict]:
    with get_conn() as c:
        r = c.execute("SELECT * FROM problems WHERE id = ?", (pid,)).fetchone()
    return _row_to_problem(r) if r else None


def get_problem_by_lc(lc_number: int) -> Optional[dict]:
    with get_conn() as c:
        r = c.execute("SELECT * FROM problems WHERE lc_number = ?", (lc_number,)).fetchone()
    return _row_to_problem(r) if r else None


def create_problem(data: dict) -> dict:
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO problems
               (lc_number, title, difficulty, tags, first_solved_at,
                notes, ai_summary,
                approach_clear, approach_desc, syntax_errors, style_issues,
                review_count, review_step, next_review_at, ease_factor,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?,
                       ?, ?,
                       ?, ?, ?, ?,
                       0, 0, ?, ?,
                       ?, ?)""",
            (
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
                data.get("next_review_at", now + 86400),
                data.get("ease_factor", DEFAULT_EASE),
                now,
                now,
            ),
        )
        pid = cur.lastrowid
        r = c.execute("SELECT * FROM problems WHERE id = ?", (pid,)).fetchone()
    return _row_to_problem(r)


def update_problem(pid: int, data: dict) -> Optional[dict]:
    fields: list[str] = []
    values: list[Any] = []
    for k in (
        "title", "difficulty", "notes", "first_solved_at",
        "approach_desc", "syntax_errors", "style_issues",
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
        return get_problem(pid)
    fields.append("updated_at = ?")
    values.append(int(time.time()))
    values.append(pid)
    with get_conn() as c:
        c.execute(f"UPDATE problems SET {', '.join(fields)} WHERE id = ?", values)
    return get_problem(pid)


def delete_problem(pid: int) -> bool:
    with get_conn() as c:
        cur = c.execute("DELETE FROM problems WHERE id = ?", (pid,))
        return cur.rowcount > 0


def list_problems(
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

    sql = "SELECT * FROM problems"
    where: list[str] = []
    args: list[Any] = []
    if difficulty:
        where.append("difficulty = ?")
        args.append(difficulty)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {sort_col} {order_sql}"

    with get_conn() as c:
        rows = c.execute(sql, args).fetchall()
    out = [_row_to_problem(r) for r in rows]
    if tag:
        # tags filtering is done in python because sqlite has no JSON predicates
        # in older builds — fine for personal-scale data.
        out = [p for p in out if tag in p["tags"]]
    return out


def list_due_today(now_ts: Optional[int] = None) -> list[dict]:
    """Return problems whose next_review_at falls anywhere up to end-of-today."""
    now_ts = now_ts or int(time.time())
    today = datetime.datetime.fromtimestamp(now_ts)
    today_end = int(today.replace(hour=23, minute=59, second=59).timestamp())
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM problems WHERE next_review_at <= ? ORDER BY next_review_at ASC",
            (today_end,),
        ).fetchall()
    return [_row_to_problem(r) for r in rows]


def list_due_in_range(start_ts: int, end_ts: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM problems WHERE next_review_at >= ? AND next_review_at <= ? "
            "ORDER BY next_review_at",
            (start_ts, end_ts),
        ).fetchall()
    return [_row_to_problem(r) for r in rows]


def apply_review(pid: int, *, review_step: int, next_review_at: int, ease_factor: float) -> None:
    now = int(time.time())
    with get_conn() as c:
        c.execute(
            """UPDATE problems
               SET review_count   = review_count + 1,
                   review_step    = ?,
                   next_review_at = ?,
                   ease_factor    = ?,
                   last_reviewed_at = ?,
                   updated_at     = ?
               WHERE id = ?""",
            (review_step, next_review_at, ease_factor, now, now, pid),
        )


def log_review(pid: int, status: str) -> None:
    with get_conn() as c:
        c.execute(
            "INSERT INTO review_logs (problem_id, status, reviewed_at) VALUES (?, ?, ?)",
            (pid, status, int(time.time())),
        )


def recent_review_logs(since_ts: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            """SELECT rl.id, rl.problem_id, rl.quiz_card_id, rl.status, rl.reviewed_at,
                      p.lc_number, p.title, p.difficulty, p.tags
               FROM review_logs rl
               JOIN problems p ON p.id = rl.problem_id
               WHERE rl.reviewed_at >= ?
               ORDER BY rl.reviewed_at DESC""",
            (since_ts,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"] or "[]")
        out.append(d)
    return out


# ---------- quiz_cards CRUD ----------
def get_card(cid: int) -> Optional[dict]:
    with get_conn() as c:
        r = c.execute("SELECT * FROM quiz_cards WHERE id = ?", (cid,)).fetchone()
    return dict(r) if r else None


def list_cards_by_problem(pid: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM quiz_cards WHERE problem_id = ? ORDER BY next_review_at, id",
            (pid,),
        ).fetchall()
    return [dict(r) for r in rows]


def count_cards_by_problem(pid: int) -> int:
    with get_conn() as c:
        return c.execute(
            "SELECT COUNT(*) FROM quiz_cards WHERE problem_id = ?", (pid,)
        ).fetchone()[0]


def create_card(data: dict) -> dict:
    """data must include: problem_id, question, next_review_at. Optional: hint, answer, category, ease_factor."""
    now = int(time.time())
    with get_conn() as c:
        cur = c.execute(
            """INSERT INTO quiz_cards
               (problem_id, question, hint, answer, category,
                review_count, review_step, next_review_at, ease_factor,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)""",
            (
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


def update_card(cid: int, data: dict) -> Optional[dict]:
    fields: list[str] = []
    values: list[Any] = []
    for k in ("question", "hint", "answer", "category"):
        if k in data and data[k] is not None:
            fields.append(f"{k} = ?")
            values.append(data[k])
    if not fields:
        return get_card(cid)
    fields.append("updated_at = ?")
    values.append(int(time.time()))
    values.append(cid)
    with get_conn() as c:
        c.execute(f"UPDATE quiz_cards SET {', '.join(fields)} WHERE id = ?", values)
    return get_card(cid)


def delete_card(cid: int) -> bool:
    with get_conn() as c:
        cur = c.execute("DELETE FROM quiz_cards WHERE id = ?", (cid,))
        return cur.rowcount > 0


def list_due_groups(now_ts: Optional[int] = None) -> list[dict]:
    """For today's review page. Returns one entry per problem that either (a)
    has at least one card due today, or (b) has no cards yet (needs AI).
    Problems whose cards are all future-scheduled are skipped entirely."""
    now_ts = now_ts or int(time.time())
    today = datetime.datetime.fromtimestamp(now_ts)
    today_end = int(today.replace(hour=23, minute=59, second=59).timestamp())
    out: list[dict] = []
    with get_conn() as c:
        problems = c.execute("SELECT * FROM problems ORDER BY lc_number").fetchall()
        for prow in problems:
            p = _row_to_problem(prow)
            total = c.execute(
                "SELECT COUNT(*) FROM quiz_cards WHERE problem_id = ?", (p["id"],)
            ).fetchone()[0]
            due_rows = c.execute(
                "SELECT * FROM quiz_cards WHERE problem_id = ? AND next_review_at <= ? "
                "ORDER BY next_review_at",
                (p["id"], today_end),
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


def list_cards_due_in_range(start_ts: int, end_ts: int) -> list[dict]:
    """For calendar."""
    with get_conn() as c:
        rows = c.execute(
            """SELECT qc.*, p.lc_number, p.title, p.difficulty
               FROM quiz_cards qc JOIN problems p ON p.id = qc.problem_id
               WHERE qc.next_review_at >= ? AND qc.next_review_at <= ?
               ORDER BY qc.next_review_at""",
            (start_ts, end_ts),
        ).fetchall()
    return [dict(r) for r in rows]


def apply_card_review(
    cid: int, *, review_step: int, next_review_at: int, ease_factor: float
) -> None:
    now = int(time.time())
    with get_conn() as c:
        c.execute(
            """UPDATE quiz_cards
               SET review_count   = review_count + 1,
                   review_step    = ?,
                   next_review_at = ?,
                   ease_factor    = ?,
                   last_reviewed_at = ?,
                   updated_at     = ?
               WHERE id = ?""",
            (review_step, next_review_at, ease_factor, now, now, cid),
        )


def log_card_review(card_id: int, problem_id: int, status: str) -> None:
    with get_conn() as c:
        c.execute(
            "INSERT INTO review_logs (problem_id, quiz_card_id, status, reviewed_at) "
            "VALUES (?, ?, ?, ?)",
            (problem_id, card_id, status, int(time.time())),
        )


# ---------- settings ----------
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
