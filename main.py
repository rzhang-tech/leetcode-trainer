"""FastAPI entry point with multi-user auth.

Auth model: email + bcrypt-hashed password. Sessions are random tokens
stored in user_sessions table; the cookie carries only the session id.
Every domain endpoint uses Depends(current_user) to resolve the user from
the session cookie and scopes DB queries by user_id.
"""
from __future__ import annotations

import datetime
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import ai_service
import auth
import database as db
import leetcode_lookup
import scheduler
from config import AI_PROVIDER, DAILY_AI_QUOTA, HOST, PORT, SESSION_LIFETIME
from models import (
    CardUpdate,
    EnglishCardUpdate,
    EnglishTranslateRequest,
    IntervalsUpdate,
    ProblemCreate,
    ProblemUpdate,
    ReviewMark,
    UserLogin,
    UserRegister,
)

BASE_DIR = Path(__file__).resolve().parent
COOKIE_NAME = "lt_session"


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    db.init_db()
    db.cleanup_expired_sessions()
    yield


app = FastAPI(title="LeetCode Trainer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# --------------- public path policy + auth middleware ---------------
PUBLIC_PATHS = {"/login", "/register", "/health"}


def _is_public(path: str) -> bool:
    return (
        path in PUBLIC_PATHS
        or path.startswith("/static")
    )


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    user = None
    sid = request.cookies.get(COOKIE_NAME)
    if sid:
        user = db.get_user_by_session(sid)
    request.state.user = user

    if not _is_public(path) and user is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


def current_user(request: Request) -> dict:
    """FastAPI dependency: returns the authenticated user dict or 401s."""
    u = getattr(request.state, "user", None)
    if not u:
        raise HTTPException(401, "Not authenticated")
    return u


# --------------- auth pages + endpoints ---------------
def _ctx(request: Request, page: str, **extra) -> dict:
    user = getattr(request.state, "user", None)
    return {
        "ai_provider": AI_PROVIDER,
        "page": page,
        "user_email": user["email"] if user else None,
        **extra,
    }


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, err: Optional[str] = None):
    # Already logged in -> redirect home
    if getattr(request.state, "user", None):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", _ctx(request, "", err=err),
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, err: Optional[str] = None):
    if getattr(request.state, "user", None):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "register.html", _ctx(request, "", err=err),
    )


@app.post("/register")
async def register_post(email: str = Form(...), password: str = Form(...)):
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email or len(email) > 254:
        return RedirectResponse("/register?err=invalid_email", status_code=303)
    if len(password) < 6:
        return RedirectResponse("/register?err=short_password", status_code=303)

    if db.get_user_by_email(email):
        return RedirectResponse("/register?err=email_taken", status_code=303)

    is_first_user = db.count_users() == 0
    user = db.create_user(email, auth.hash_password(password), is_admin=is_first_user)

    # First user adopts any pre-multi-user data so it doesn't disappear.
    if is_first_user:
        db.adopt_orphan_data(user["id"])

    sid = auth.create_session(user["id"], SESSION_LIFETIME)
    db.update_last_login(user["id"])
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        COOKIE_NAME, sid, httponly=True, samesite="lax",
        max_age=SESSION_LIFETIME,
    )
    return resp


@app.post("/login")
async def login_post(email: str = Form(...), password: str = Form(...)):
    email = (email or "").strip().lower()
    user = db.get_user_by_email(email)
    if not user or not auth.verify_password(password, user["password_hash"]):
        return RedirectResponse("/login?err=bad_credentials", status_code=303)

    sid = auth.create_session(user["id"], SESSION_LIFETIME)
    db.update_last_login(user["id"])
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        COOKIE_NAME, sid, httponly=True, samesite="lax",
        max_age=SESSION_LIFETIME,
    )
    return resp


@app.post("/logout")
async def logout_post(request: Request):
    sid = request.cookies.get(COOKIE_NAME)
    auth.revoke_session(sid)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.get("/health")
async def health():
    return {"ok": True, "provider": AI_PROVIDER}


@app.get("/api/me")
async def api_me(user: dict = Depends(current_user)):
    return {
        "id": user["id"],
        "email": user["email"],
        "is_admin": user["is_admin"],
        "daily_ai_calls": user["daily_ai_calls"],
        "daily_ai_quota": DAILY_AI_QUOTA,
    }


# --------------- HTML pages ---------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", _ctx(request, "today"))


@app.get("/add", response_class=HTMLResponse)
async def add_page(request: Request):
    return templates.TemplateResponse(request, "add.html", _ctx(request, "add"))


@app.get("/list", response_class=HTMLResponse)
async def list_page(request: Request):
    return templates.TemplateResponse(request, "list.html", _ctx(request, "list"))


@app.get("/review/{pid}", response_class=HTMLResponse)
async def review_page(request: Request, pid: int):
    user = current_user(request)
    if not db.get_problem(pid, user["id"]):
        raise HTTPException(404)
    return templates.TemplateResponse(
        request, "review.html", _ctx(request, "review", problem_id=pid),
    )


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    return templates.TemplateResponse(request, "calendar.html", _ctx(request, "calendar"))


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse(request, "settings.html", _ctx(request, "settings"))


@app.get("/english", response_class=HTMLResponse)
async def english_page(request: Request):
    return templates.TemplateResponse(request, "english.html", _ctx(request, "english"))


# --------------- JSON API: English flashcards ---------------
@app.post("/api/english/translate-and-save")
async def api_english_translate(req: EnglishTranslateRequest, user: dict = Depends(current_user)):
    _consume_ai_quota_or_403(user)
    prompt_text = ai_service.ENGLISH_TRANSLATE_TEMPLATE.format(prompt=req.prompt)
    try:
        text = await ai_service.chat(prompt_text)
        parsed = ai_service.parse_json(text)
    except Exception as e:
        raise HTTPException(502, f"AI call failed: {e}") from None
    answer = (parsed.get("english") or "").strip() if isinstance(parsed, dict) else ""
    if not answer:
        raise HTTPException(502, "AI returned empty translation")
    next_at = scheduler.initial_next_review(int(time.time()))
    return db.create_english_card({
        "prompt": req.prompt.strip(),
        "answer": answer,
        "next_review_at": next_at,
    }, user["id"])


@app.get("/api/english/cards")
async def api_english_cards_list(
    due_only: bool = False, user: dict = Depends(current_user),
):
    return db.list_english_cards(user["id"], due_only=due_only)


@app.put("/api/english/cards/{cid}")
async def api_english_card_update(
    cid: int, data: EnglishCardUpdate, user: dict = Depends(current_user),
):
    if not db.get_english_card(cid, user["id"]):
        raise HTTPException(404)
    return db.update_english_card(cid, user["id"], data.model_dump(exclude_unset=True))


@app.delete("/api/english/cards/{cid}")
async def api_english_card_delete(cid: int, user: dict = Depends(current_user)):
    if not db.delete_english_card(cid, user["id"]):
        raise HTTPException(404)
    return {"ok": True}


@app.post("/api/english/cards/{cid}/mark")
async def api_english_card_mark(
    cid: int, mark: ReviewMark, user: dict = Depends(current_user),
):
    card = db.get_english_card(cid, user["id"])
    if not card:
        raise HTTPException(404)
    new_step, next_at, new_ef = scheduler.compute_next(
        current_step=card["review_step"],
        ease_factor=card["ease_factor"],
        status=mark.status,
    )
    db.apply_english_review(
        cid, user["id"],
        review_step=new_step, next_review_at=next_at, ease_factor=new_ef,
    )
    return db.get_english_card(cid, user["id"])


# --------------- JSON API: problems ---------------
@app.post("/api/problems")
async def api_problems_create(data: ProblemCreate, user: dict = Depends(current_user)):
    if db.get_problem_by_lc(data.lc_number, user["id"]):
        raise HTTPException(409, f"Problem #{data.lc_number} already exists in your library")
    payload = data.model_dump()
    if not payload.get("first_solved_at"):
        payload["first_solved_at"] = int(time.time())
    payload["next_review_at"] = scheduler.initial_next_review(payload["first_solved_at"])
    return db.create_problem(payload, user["id"])


@app.get("/api/problems")
async def api_problems_list(
    user: dict = Depends(current_user),
    difficulty: Optional[str] = None,
    tag: Optional[str] = None,
    sort: str = "lc_number",
    order: str = "asc",
):
    return db.list_problems(
        user["id"], difficulty=difficulty, tag=tag, sort=sort, order=order,
    )


@app.get("/api/problems/by-lc/{lc_number}")
async def api_problems_by_lc(lc_number: int, user: dict = Depends(current_user)):
    p = db.get_problem_by_lc(lc_number, user["id"])
    if not p:
        raise HTTPException(404)
    return p


@app.get("/api/problems/{pid}")
async def api_problems_get(pid: int, user: dict = Depends(current_user)):
    p = db.get_problem(pid, user["id"])
    if not p:
        raise HTTPException(404)
    return p


@app.put("/api/problems/{pid}")
async def api_problems_update(pid: int, data: ProblemUpdate, user: dict = Depends(current_user)):
    if not db.get_problem(pid, user["id"]):
        raise HTTPException(404)
    return db.update_problem(pid, user["id"], data.model_dump(exclude_unset=True))


@app.delete("/api/problems/{pid}")
async def api_problems_delete(pid: int, user: dict = Depends(current_user)):
    if not db.delete_problem(pid, user["id"]):
        raise HTTPException(404)
    return {"ok": True}


@app.get("/api/leetcode-meta/{lc_number}")
async def api_leetcode_meta(lc_number: int, user: dict = Depends(current_user)):
    """Look up canonical title / difficulty / tags from leetcode.com."""
    try:
        meta = await leetcode_lookup.get_meta(lc_number)
    except Exception as e:
        raise HTTPException(502, f"LeetCode API unavailable: {e}") from None
    if not meta:
        raise HTTPException(404, f"LC {lc_number} not in public catalog (premium or wrong number)")
    if meta.get("paid_only"):
        raise HTTPException(403, f"LC {lc_number} is a premium-only problem; can't auto-fetch")
    return meta


# --------------- JSON API: today / review / cards ---------------
def _today_start_ts() -> int:
    now = datetime.datetime.now()
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


@app.get("/api/today")
async def api_today(user: dict = Depends(current_user)):
    groups = db.list_due_groups(user["id"])
    due_count = sum(g["due_count"] for g in groups)
    today_start = _today_start_ts()
    today_end = today_start + 86400
    logs = db.recent_review_logs(user["id"], today_start)
    completed_count = sum(
        1 for l in logs
        if l["reviewed_at"] < today_end and l.get("quiz_card_id")
    )
    return {
        "groups": groups,
        "due_count": due_count,
        "completed_count": completed_count,
    }


@app.get("/api/problems/{pid}/cards")
async def api_cards_list(pid: int, user: dict = Depends(current_user)):
    if not db.get_problem(pid, user["id"]):
        raise HTTPException(404)
    return db.list_cards_by_problem(pid, user["id"])


def _consume_ai_quota_or_403(user: dict) -> None:
    allowed, used = db.check_and_consume_ai_quota(user["id"], DAILY_AI_QUOTA)
    if not allowed:
        raise HTTPException(
            429,
            f"Daily AI quota of {DAILY_AI_QUOTA} reached ({used} used). "
            "Resets at UTC midnight.",
        )


@app.post("/api/problems/{pid}/cards/generate")
async def api_cards_generate(pid: int, user: dict = Depends(current_user)):
    """Run the quiz prompt and persist returned questions as new cards (append)."""
    p = db.get_problem(pid, user["id"])
    if not p:
        raise HTTPException(404)

    _consume_ai_quota_or_403(user)

    if p.get("approach_clear", True):
        approach_status = "User has a clear approach; do not waste a question on 'describe the approach'."
        approach_desc_section = "(skip)"
        must_describe_approach = ""
    else:
        approach_status = (
            "User is unfamiliar with the approach to this problem and explicitly wants it tested heavily."
        )
        approach_desc_section = (
            "User's own description of the approach (may be inaccurate or incomplete; "
            "design a question that surfaces gaps):\n"
            + (p.get("approach_desc") or "(not yet filled)")
        )
        must_describe_approach = (
            "7. **Mandatory**: include one open-ended question asking the user to describe "
            "the core approach in their own words — key idea, key steps, complexity. "
            "This forces active recall.\n"
        )

    prompt = ai_service.QUIZ_TEMPLATE.format(
        lc_number=p["lc_number"],
        title=p["title"],
        approach_status=approach_status,
        approach_desc_section=approach_desc_section,
        syntax_errors=p.get("syntax_errors") or "(none)",
        style_issues=p.get("style_issues") or "(none)",
        notes=p.get("notes") or "(none)",
        must_describe_approach=must_describe_approach,
    )
    try:
        text = await ai_service.chat(prompt)
        parsed = ai_service.parse_json(text)
    except Exception as e:
        raise HTTPException(502, f"AI call failed: {e}") from None
    questions = parsed.get("questions", []) if isinstance(parsed, dict) else []
    next_at = scheduler.initial_next_review(int(time.time()))
    created: list[dict] = []
    for q in questions:
        if not isinstance(q, dict) or not q.get("question"):
            continue
        card = db.create_card({
            "problem_id": pid,
            "question": q.get("question"),
            "hint": q.get("hint"),
            "answer": q.get("answer"),
            "category": q.get("category"),
            "next_review_at": next_at,
        }, user["id"])
        created.append(card)
    return {"created": created, "count": len(created)}


@app.put("/api/cards/{cid}")
async def api_card_update(cid: int, data: CardUpdate, user: dict = Depends(current_user)):
    if not db.get_card(cid, user["id"]):
        raise HTTPException(404)
    return db.update_card(cid, user["id"], data.model_dump(exclude_unset=True))


@app.delete("/api/cards/{cid}")
async def api_card_delete(cid: int, user: dict = Depends(current_user)):
    if not db.delete_card(cid, user["id"]):
        raise HTTPException(404)
    return {"ok": True}


@app.post("/api/cards/{cid}/mark")
async def api_card_mark(cid: int, mark: ReviewMark, user: dict = Depends(current_user)):
    card = db.get_card(cid, user["id"])
    if not card:
        raise HTTPException(404)
    new_step, next_at, new_ef = scheduler.compute_next(
        current_step=card["review_step"],
        ease_factor=card["ease_factor"],
        status=mark.status,
    )
    db.apply_card_review(
        cid, user["id"], review_step=new_step, next_review_at=next_at, ease_factor=new_ef,
    )
    db.log_card_review(cid, card["problem_id"], mark.status)
    return db.get_card(cid, user["id"])


@app.get("/api/weekly-report")
async def api_weekly_report(user: dict = Depends(current_user)):
    _consume_ai_quota_or_403(user)
    since = int(time.time()) - 7 * 86400
    logs = db.recent_review_logs(user["id"], since)
    new_problems = [
        p for p in db.list_problems(user["id"]) if p["first_solved_at"] >= since
    ]
    new_summary = "\n".join(
        f"- LC{p['lc_number']} {p['title']} ({p['difficulty']}, tags: {','.join(p['tags']) or 'none'})"
        for p in new_problems
    ) or "(no new problems this week)"
    log_lines = []
    for l in logs:
        ts = datetime.datetime.fromtimestamp(l["reviewed_at"]).strftime("%Y-%m-%d %H:%M")
        log_lines.append(
            f"- LC{l['lc_number']} {l['title']}: {l['status']} @ {ts}"
        )
    log_summary = "\n".join(log_lines) or "(no review activity this week)"

    prompt = ai_service.WEEKLY_REPORT_TEMPLATE.format(
        new_problems=new_summary, review_logs=log_summary
    )
    try:
        text = await ai_service.chat(prompt)
    except Exception as e:
        raise HTTPException(502, f"AI call failed: {e}") from None
    return {
        "report": text,
        "new_count": len(new_problems),
        "review_count": len(logs),
    }


# --------------- JSON API: calendar / settings ---------------
@app.get("/api/calendar")
async def api_calendar(year: int, month: int, user: dict = Depends(current_user)):
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")
    start = datetime.datetime(year, month, 1)
    end = (
        datetime.datetime(year + 1, 1, 1)
        if month == 12
        else datetime.datetime(year, month + 1, 1)
    )
    rows = db.list_cards_due_in_range(
        user["id"], int(start.timestamp()), int(end.timestamp()) - 1,
    )
    by_day: dict[str, dict[int, dict]] = {}
    for c in rows:
        d = datetime.datetime.fromtimestamp(c["next_review_at"]).strftime("%Y-%m-%d")
        bucket = by_day.setdefault(d, {})
        item = bucket.setdefault(c["problem_id"], {
            "id": c["problem_id"],
            "lc_number": c["lc_number"],
            "title": c["title"],
            "difficulty": c["difficulty"],
            "card_count": 0,
        })
        item["card_count"] += 1
    return {day: list(items.values()) for day, items in by_day.items()}


@app.get("/api/settings")
async def api_settings_get(user: dict = Depends(current_user)):
    return {
        "intervals": scheduler.get_intervals(),
        "ai_provider": AI_PROVIDER,
        "daily_ai_quota": DAILY_AI_QUOTA,
        "daily_ai_calls": user["daily_ai_calls"],
    }


@app.put("/api/settings/intervals")
async def api_settings_intervals(
    data: IntervalsUpdate, user: dict = Depends(current_user),
):
    if any(i < 0 for i in data.intervals):
        raise HTTPException(400, "intervals must be non-negative integers")
    db.set_setting("intervals", data.intervals)
    return {"ok": True, "intervals": data.intervals}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
