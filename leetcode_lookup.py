"""LeetCode public-API helper.

We hit two unauthenticated endpoints on leetcode.com:

  GET  /api/problems/all/      — full question list (id, title, slug, difficulty).
                                 Big response (~1MB), cache 24h.
  POST /graphql                — per-question topic tags by slug.

`get_meta(lc_number)` is the only function the rest of the app uses.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx

_ALL_URL = "https://leetcode.com/api/problems/all/"
_GQL_URL = "https://leetcode.com/graphql"
_UA = "Mozilla/5.0 (leetcode-trainer; personal use)"

# LC encodes difficulty as 1/2/3 in the all-problems list.
_DIFF = {1: "easy", 2: "medium", 3: "hard"}

# In-process cache of the full problems list (lc_number -> {title, slug, difficulty}).
_problems_cache: Optional[dict[int, dict]] = None
_cache_at: float = 0.0
_CACHE_TTL = 24 * 3600  # 24 hours

_TAGS_QUERY = """\
query getTopicTags($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    topicTags { slug }
  }
}
"""


async def _fetch_problems_list() -> dict[int, dict]:
    global _problems_cache, _cache_at
    if _problems_cache is not None and (time.time() - _cache_at) < _CACHE_TTL:
        return _problems_cache

    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(_ALL_URL, headers={"User-Agent": _UA})
    r.raise_for_status()
    data = r.json()

    out: dict[int, dict] = {}
    for q in data.get("stat_status_pairs", []):
        stat = q.get("stat") or {}
        try:
            lc_num = int(stat.get("frontend_question_id"))
        except (TypeError, ValueError):
            continue  # skip premium/non-numeric (e.g. dash-separated) IDs
        title = stat.get("question__title")
        slug = stat.get("question__title_slug")
        diff_level = (q.get("difficulty") or {}).get("level")
        paid_only = q.get("paid_only", False)
        if not title or not slug:
            continue
        out[lc_num] = {
            "title": title,
            "slug": slug,
            "difficulty": _DIFF.get(diff_level, "medium"),
            "paid_only": bool(paid_only),
        }

    _problems_cache = out
    _cache_at = time.time()
    return out


async def _fetch_tags(slug: str) -> list[str]:
    payload = {
        "query": _TAGS_QUERY,
        "variables": {"titleSlug": slug},
        "operationName": "getTopicTags",
    }
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            _GQL_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _UA,
                "Referer": f"https://leetcode.com/problems/{slug}/",
            },
        )
    r.raise_for_status()
    body = r.json()
    q = (body.get("data") or {}).get("question") or {}
    return [t["slug"] for t in (q.get("topicTags") or []) if t.get("slug")]


async def get_meta(lc_number: int) -> Optional[dict]:
    """Look up a LeetCode problem by its frontend question number.

    Returns a dict {lc_number, title, difficulty, tags, slug, paid_only}
    or None if the number doesn't exist in the public list.
    """
    problems = await _fetch_problems_list()
    p = problems.get(int(lc_number))
    if not p:
        return None
    try:
        tags = await _fetch_tags(p["slug"])
    except Exception:
        # Non-fatal: empty tags is acceptable; user can re-save later.
        tags = []
    return {
        "lc_number": int(lc_number),
        "title": p["title"],
        "difficulty": p["difficulty"],
        "tags": tags,
        "slug": p["slug"],
        "paid_only": p["paid_only"],
    }
