"""Unified async LLM client.

`chat(prompt) -> str` is the only entry point callers should use; it dispatches
to one of three providers based on `AI_PROVIDER`. We talk to each provider's
REST API directly through `httpx` instead of pulling in `google-genai` /
`openai` / `anthropic` SDKs — that keeps the dependency footprint to httpx
alone, which matters on a 1GB box.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from config import (
    AI_PROVIDER,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    GEMINI_MODEL,
    GOOGLE_API_KEY,
    VERTEX_LOCATION,
    VERTEX_MODEL,
    VERTEX_PROJECT,
)

# AI calls can be slow; allow a generous timeout but cap connect time.
TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class AIError(RuntimeError):
    """Raised for any AI provider failure (config, network, parse)."""


# ---------------- providers ----------------
async def _chat_gemini(prompt: str) -> str:
    if not GOOGLE_API_KEY:
        raise AIError("GOOGLE_API_KEY is not configured")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4},
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            url,
            params={"key": GOOGLE_API_KEY},
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    if r.status_code >= 400:
        raise AIError(f"Gemini API {r.status_code}: {r.text[:300]}")
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise AIError(f"Unexpected Gemini response shape: {e}; raw={data}") from None


async def _chat_deepseek(prompt: str) -> str:
    if not DEEPSEEK_API_KEY:
        raise AIError("DEEPSEEK_API_KEY is not configured")
    url = "https://api.deepseek.com/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
        )
    if r.status_code >= 400:
        raise AIError(f"DeepSeek API {r.status_code}: {r.text[:300]}")
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise AIError(f"Unexpected DeepSeek response shape: {e}; raw={data}") from None


# --- Vertex AI -------------------------------------------------------------
# Vertex auth uses OAuth2 access tokens (not a static API key). We rely on
# Google's Application Default Credentials so users can either point
# GOOGLE_APPLICATION_CREDENTIALS at a service-account JSON or run
# `gcloud auth application-default login` locally — same code path either way.
# `google-auth` is the only extra dep; importing it lazily keeps non-vertex
# users from needing it installed.
_vertex_creds = None
_vertex_lock: "asyncio.Lock | None" = None


async def _get_vertex_token() -> str:
    global _vertex_creds, _vertex_lock
    if _vertex_lock is None:
        _vertex_lock = asyncio.Lock()
    async with _vertex_lock:
        if _vertex_creds is None:
            try:
                from google.auth import default as _gauth_default  # type: ignore
            except ImportError as e:
                raise AIError(
                    "google-auth is required for the vertex provider: pip install google-auth"
                ) from e
            try:
                creds, _proj = _gauth_default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            except Exception as e:
                raise AIError(
                    "Failed to load Google ADC credentials. Set GOOGLE_APPLICATION_CREDENTIALS "
                    f"or run `gcloud auth application-default login`. Original error: {e}"
                ) from None
            _vertex_creds = creds
        if not _vertex_creds.valid:
            from google.auth.transport.requests import Request  # type: ignore

            try:
                await asyncio.to_thread(_vertex_creds.refresh, Request())
            except Exception as e:
                raise AIError(f"Failed to refresh Vertex token: {e}") from None
        return _vertex_creds.token


async def _chat_vertex(prompt: str) -> str:
    if not VERTEX_PROJECT:
        raise AIError("VERTEX_PROJECT is not configured")
    token = await _get_vertex_token()
    url = (
        f"https://{VERTEX_LOCATION}-aiplatform.googleapis.com/v1/"
        f"projects/{VERTEX_PROJECT}/locations/{VERTEX_LOCATION}/"
        f"publishers/google/models/{VERTEX_MODEL}:generateContent"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4},
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    if r.status_code >= 400:
        raise AIError(f"Vertex API {r.status_code}: {r.text[:300]}")
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise AIError(f"Unexpected Vertex response shape: {e}; raw={data}") from None


async def _chat_claude(prompt: str) -> str:
    if not ANTHROPIC_API_KEY:
        raise AIError("ANTHROPIC_API_KEY is not configured")
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            url,
            json=payload,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
    if r.status_code >= 400:
        raise AIError(f"Claude API {r.status_code}: {r.text[:300]}")
    data = r.json()
    try:
        # message API returns a list of content blocks; we take the first text block.
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"]
        raise KeyError("no text block")
    except (KeyError, IndexError, TypeError) as e:
        raise AIError(f"Unexpected Claude response shape: {e}; raw={data}") from None


async def chat(prompt: str) -> str:
    """Single entry point. Routes by AI_PROVIDER."""
    if AI_PROVIDER == "gemini":
        return await _chat_gemini(prompt)
    if AI_PROVIDER == "vertex":
        return await _chat_vertex(prompt)
    if AI_PROVIDER == "deepseek":
        return await _chat_deepseek(prompt)
    if AI_PROVIDER == "claude":
        return await _chat_claude(prompt)
    raise AIError(f"Unknown AI_PROVIDER: {AI_PROVIDER!r}")


# ---------------- response helpers ----------------
def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # drop the opening fence (``` or ```json) and trailing fence
        first_nl = t.find("\n")
        t = t[first_nl + 1 :] if first_nl != -1 else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def parse_json(text: str) -> Any:
    """Extract a JSON object from a model response, tolerating code fences and
    leading/trailing prose."""
    cleaned = _strip_json_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


# ---------------- prompt templates ----------------
QUIZ_TEMPLATE = """You are a LeetCode interview coach. Based on the user's structured study notes for one problem, generate 3-5 precise quiz questions that test whether the user has truly mastered these knowledge points.

Problem: LeetCode {lc_number} {title}

[Approach clarity] {approach_status}
{approach_desc_section}

[Syntax errors / language pitfalls the user hit on this problem]
{syntax_errors}

[Style / optimization opportunities (the user's original code wasn't wrong but could be better)]
{style_issues}

[Other notes]
{notes}

Rules:
1. Questions must be **specific** — e.g. "write a code snippet that does X", "what does this code output", "what is the time complexity of Y", "what's the difference between these two approaches".
2. **Prioritize the 'Syntax' and 'Style' sections** — these are concrete pitfalls the user has hit, more useful than generic algorithm trivia.
3. Mix categories across the options below.
4. Questions must be directly answerable, not too open-ended.
5. If a section says "(none)", do not force questions out of that category.
6. Match the language of your output (questions, hints, answers) to the language the user wrote their notes in. If the notes are in Chinese, answer in Chinese; English notes → English output.
{must_describe_approach}
Return ONLY JSON, no explanation text and no code fences:
{{
  "questions": [
    {{
      "question": "...",
      "hint": "...(omit field if no hint needed)",
      "answer": "...",
      "category": "Algorithm"
    }}
  ]
}}

`category` MUST be exactly one of: "Approach", "Algorithm", "Syntax", "Pitfall".
"""

ENGLISH_TRANSLATE_TEMPLATE = """The user wants to express the following idea in natural, idiomatic English. Give a single best phrasing — concise, common, and sounding like a native speaker would say it in everyday context. No alternatives, no commentary, no register tags.

User's intent (typically Chinese): {prompt}

Return ONLY JSON, no explanation, no code fences:
{{"english": "the natural English phrasing"}}
"""

WEEKLY_REPORT_TEMPLATE = """You are a LeetCode learning coach. Below is the user's data from the past 7 days. Write a concise weekly report covering:

1. New problems this week (count, difficulty distribution)
2. Review activity (total card reviews, retention rate)
3. Recurring weak spots (problems repeatedly marked "forgot")
4. Recommended focus for next week (what to re-emphasize, what gaps to address)

Data:

[New problems]
{new_problems}

[Review log]
{review_logs}

Output Markdown with `##` section headings. Be concise — don't restate the raw data; give actionable suggestions.

Match the report language to the language used in the data above (titles, etc.). If the data is in Chinese, write the report in Chinese; otherwise English.
"""
