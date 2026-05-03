"""FastAPI entry point.

Routes split into:
  - HTML pages: render Jinja templates, only need `request` in context.
  - JSON API:   /api/* — consumed by static/js/app.js.

Auth model: a single shared token. If AUTH_TOKEN is empty, auth is disabled
(handy for local dev). Otherwise, every non-public request must carry either
a matching `auth_token` cookie or `X-Auth-Token` header. /login sets the cookie.
"""
from __future__ import annotations

import datetime
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import ai_service
import database as db
import leetcode_lookup
import scheduler
from config import AI_PROVIDER, AUTH_TOKEN, HOST, PORT
from models import CardUpdate, IntervalsUpdate, ProblemCreate, ProblemUpdate, ReviewMark

BASE_DIR = Path(__file__).resolve().parent
COOKIE_NAME = "auth_token"


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    db.init_db()
    yield


app = FastAPI(title="LeetCode Trainer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ---------------- auth middleware ----------------
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if AUTH_TOKEN:
        path = request.url.path
        public = (
            path in ("/login", "/health")
            or path.startswith("/static")
        )
        if not public:
            cookie = request.cookies.get(COOKIE_NAME)
            header = request.headers.get("X-Auth-Token")
            if cookie != AUTH_TOKEN and header != AUTH_TOKEN:
                if path.startswith("/api/"):
                    return JSONResponse({"detail": "未认证"}, status_code=401)
                return RedirectResponse("/login", status_code=303)
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, err: Optional[str] = None):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"ai_provider": AI_PROVIDER, "page": "", "err": err},
    )


@app.post("/login")
async def login_post(token: str = Form(...)):
    if AUTH_TOKEN and token != AUTH_TOKEN:
        return RedirectResponse("/login?err=1", status_code=303)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        AUTH_TOKEN or "ok",
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return resp


@app.get("/health")
async def health():
    return {"ok": True, "provider": AI_PROVIDER}


# ---------------- HTML pages ----------------
def _ctx(page: str, **extra) -> dict:
    return {"ai_provider": AI_PROVIDER, "page": page, **extra}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", _ctx("today"))


@app.get("/add", response_class=HTMLResponse)
async def add_page(request: Request):
    return templates.TemplateResponse(request, "add.html", _ctx("add"))


@app.get("/list", response_class=HTMLResponse)
async def list_page(request: Request):
    return templates.TemplateResponse(request, "list.html", _ctx("list"))


@app.get("/review/{pid}", response_class=HTMLResponse)
async def review_page(request: Request, pid: int):
    if not db.get_problem(pid):
        raise HTTPException(404)
    return templates.TemplateResponse(
        request, "review.html", _ctx("review", problem_id=pid)
    )


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    return templates.TemplateResponse(request, "calendar.html", _ctx("calendar"))


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse(request, "settings.html", _ctx("settings"))


# ---------------- JSON API: problems ----------------
@app.post("/api/problems")
async def api_problems_create(data: ProblemCreate):
    if db.get_problem_by_lc(data.lc_number):
        raise HTTPException(409, f"题号 {data.lc_number} 已存在")
    payload = data.model_dump()
    if not payload.get("first_solved_at"):
        payload["first_solved_at"] = int(time.time())
    payload["next_review_at"] = scheduler.initial_next_review(payload["first_solved_at"])
    return db.create_problem(payload)


@app.get("/api/problems")
async def api_problems_list(
    difficulty: Optional[str] = None,
    tag: Optional[str] = None,
    sort: str = "lc_number",
    order: str = "asc",
):
    return db.list_problems(difficulty=difficulty, tag=tag, sort=sort, order=order)


@app.get("/api/problems/by-lc/{lc_number}")
async def api_problems_by_lc(lc_number: int):
    p = db.get_problem_by_lc(lc_number)
    if not p:
        raise HTTPException(404)
    return p


@app.get("/api/leetcode-meta/{lc_number}")
async def api_leetcode_meta(lc_number: int):
    """Look up canonical title / difficulty / tags from leetcode.com.

    Used by the add-problem form to auto-fill (and lock) those fields so the
    user only ever has to enter the question number.
    """
    try:
        meta = await leetcode_lookup.get_meta(lc_number)
    except Exception as e:
        raise HTTPException(502, f"LeetCode 接口不可用: {e}") from None
    if not meta:
        raise HTTPException(404, f"LC {lc_number} 不在公开题库中（付费题或题号错误）")
    if meta.get("paid_only"):
        raise HTTPException(403, f"LC {lc_number} 是付费会员题，无法自动获取信息")
    return meta


@app.get("/api/problems/{pid}")
async def api_problems_get(pid: int):
    p = db.get_problem(pid)
    if not p:
        raise HTTPException(404)
    return p


@app.put("/api/problems/{pid}")
async def api_problems_update(pid: int, data: ProblemUpdate):
    if not db.get_problem(pid):
        raise HTTPException(404)
    return db.update_problem(pid, data.model_dump(exclude_unset=True))


@app.delete("/api/problems/{pid}")
async def api_problems_delete(pid: int):
    if not db.delete_problem(pid):
        raise HTTPException(404)
    return {"ok": True}


# ---------------- JSON API: review flow ----------------
def _today_start_ts() -> int:
    now = datetime.datetime.now()
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


@app.get("/api/today")
async def api_today():
    """Today's review, grouped by problem.

    Each group is either: due cards under that problem, OR a problem with no
    cards yet (needs_generation=True) so the user is nudged to run AI.
    """
    groups = db.list_due_groups()
    due_count = sum(g["due_count"] for g in groups)
    today_start = _today_start_ts()
    today_end = today_start + 86400
    logs = db.recent_review_logs(today_start)
    completed_count = sum(
        1 for l in logs
        if l["reviewed_at"] < today_end and l.get("quiz_card_id")
    )
    return {
        "groups": groups,
        "due_count": due_count,
        "completed_count": completed_count,
    }


# ---------------- JSON API: AI features ----------------
@app.get("/api/problems/{pid}/cards")
async def api_cards_list(pid: int):
    if not db.get_problem(pid):
        raise HTTPException(404)
    return db.list_cards_by_problem(pid)


@app.post("/api/problems/{pid}/cards/generate")
async def api_cards_generate(pid: int):
    """Run the quiz prompt and persist returned questions as new cards (append).

    Existing cards (with their review history) are untouched.
    """
    p = db.get_problem(pid)
    if not p:
        raise HTTPException(404)

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
        syntax_errors=p.get("syntax_errors") or "(无)",
        style_issues=p.get("style_issues") or "(无)",
        notes=p.get("notes") or "(无)",
        must_describe_approach=must_describe_approach,
    )
    try:
        text = await ai_service.chat(prompt)
        parsed = ai_service.parse_json(text)
    except Exception as e:
        raise HTTPException(502, f"AI 调用失败: {e}") from None
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
        })
        created.append(card)
    return {"created": created, "count": len(created)}


@app.put("/api/cards/{cid}")
async def api_card_update(cid: int, data: CardUpdate):
    if not db.get_card(cid):
        raise HTTPException(404)
    return db.update_card(cid, data.model_dump(exclude_unset=True))


@app.delete("/api/cards/{cid}")
async def api_card_delete(cid: int):
    if not db.delete_card(cid):
        raise HTTPException(404)
    return {"ok": True}


@app.post("/api/cards/{cid}/mark")
async def api_card_mark(cid: int, mark: ReviewMark):
    card = db.get_card(cid)
    if not card:
        raise HTTPException(404)
    new_step, next_at, new_ef = scheduler.compute_next(
        current_step=card["review_step"],
        ease_factor=card["ease_factor"],
        status=mark.status,
    )
    db.apply_card_review(
        cid, review_step=new_step, next_review_at=next_at, ease_factor=new_ef
    )
    db.log_card_review(cid, card["problem_id"], mark.status)
    return db.get_card(cid)


@app.get("/api/weekly-report")
async def api_weekly_report():
    since = int(time.time()) - 7 * 86400
    logs = db.recent_review_logs(since)
    new_problems = [p for p in db.list_problems() if p["first_solved_at"] >= since]

    new_summary = "\n".join(
        f"- LC{p['lc_number']} {p['title']} ({p['difficulty']}, 标签: {','.join(p['tags']) or '无'})"
        for p in new_problems
    ) or "(本周无新题)"
    log_lines = []
    for l in logs:
        ts = datetime.datetime.fromtimestamp(l["reviewed_at"]).strftime("%Y-%m-%d %H:%M")
        log_lines.append(
            f"- LC{l['lc_number']} {l['title']}: {l['status']} @ {ts}"
        )
    log_summary = "\n".join(log_lines) or "(本周无复习记录)"

    prompt = ai_service.WEEKLY_REPORT_TEMPLATE.format(
        new_problems=new_summary, review_logs=log_summary
    )
    try:
        text = await ai_service.chat(prompt)
    except Exception as e:
        raise HTTPException(502, f"AI 调用失败: {e}") from None
    return {
        "report": text,
        "new_count": len(new_problems),
        "review_count": len(logs),
    }


# ---------------- JSON API: calendar / settings ----------------
@app.get("/api/calendar")
async def api_calendar(year: int, month: int):
    if not (1 <= month <= 12):
        raise HTTPException(400, "month 必须在 1..12 之间")
    start = datetime.datetime(year, month, 1)
    end = (
        datetime.datetime(year + 1, 1, 1)
        if month == 12
        else datetime.datetime(year, month + 1, 1)
    )
    rows = db.list_cards_due_in_range(
        int(start.timestamp()), int(end.timestamp()) - 1
    )
    # Aggregate per (day, problem) so the same problem with N due cards on
    # the same day collapses to one entry with a card count.
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
async def api_settings_get():
    return {
        "intervals": scheduler.get_intervals(),
        "ai_provider": AI_PROVIDER,
    }


@app.put("/api/settings/intervals")
async def api_settings_intervals(data: IntervalsUpdate):
    if any(i < 0 for i in data.intervals):
        raise HTTPException(400, "间隔必须是非负整数")
    db.set_setting("intervals", data.intervals)
    return {"ok": True, "intervals": data.intervals}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
