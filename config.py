"""Configuration loaded from environment / .env file.

All knobs the user might tweak are read from env. Defaults are friendly for
local development; a 1GB Ubuntu box only needs HOST/PORT/AI_PROVIDER set.
"""
from __future__ import annotations

import os
from pathlib import Path

# Load .env if python-dotenv is installed; missing dotenv is non-fatal so the
# service can also run with real env vars injected by systemd.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ----- AI provider selection -----
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")

# Vertex AI (Google Cloud). Authentication is via Application Default
# Credentials — set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON
# path, or run `gcloud auth application-default login` for local dev.
VERTEX_PROJECT = os.getenv("VERTEX_PROJECT", "").strip()
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1").strip()
VERTEX_MODEL = os.getenv("VERTEX_MODEL", "gemini-2.5-flash")

# ----- Server -----
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8765"))

# Optional shared-secret cookie auth. Empty = disabled (local dev convenience).
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "").strip()

# ----- Database -----
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "tracker.db"))

# ----- Spaced-repetition defaults (overridable via /settings, persisted in DB) -----
DEFAULT_INTERVALS = [1, 2, 4, 7, 15, 30, 60]  # days
DEFAULT_EASE = 2.5
EASE_PENALTY = 0.2  # subtracted on "forgot"
EASE_BONUS = 0.05   # added on "remembered"
EASE_MIN = 1.3
EASE_MAX = 3.0
