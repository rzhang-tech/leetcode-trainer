"""Spaced-repetition scheduler (Ebbinghaus-flavoured, Anki-style overdue handling).

State carried per card:
  review_step      -- index into the configured intervals list
  ease_factor      -- multiplier on the base interval (clamped to [1.3, 3.0])
  last_reviewed_at -- unix timestamp of the previous review (used for overdue calc)

Transitions on a review:
  remembered -> step += 1 (capped at last index), ease += 0.05
               If overdue, next interval = max(step-based, actual_elapsed * ease)
               so recalling after a long gap earns a proportionally longer interval.
  fuzzy      -> step unchanged, ease unchanged
  forgot     -> step = 0, ease -= 0.2
               next_review_at is clamped to start of tomorrow so the card never
               reappears in the same day's session (fixes the "low ease = 12h" bug).

The actual delay used is `intervals[new_step] * (ease / 2.5)` days as the floor,
extended when the card was reviewed late.
"""
from __future__ import annotations

import datetime
import time
from typing import Literal, Optional

from config import (
    DEFAULT_EASE,
    DEFAULT_INTERVALS,
    EASE_BONUS,
    EASE_MAX,
    EASE_MIN,
    EASE_PENALTY,
)
from database import get_setting

Status = Literal["remembered", "fuzzy", "forgot"]


def get_intervals() -> list[int]:
    intervals = get_setting("intervals", DEFAULT_INTERVALS)
    if not isinstance(intervals, list) or not intervals:
        return list(DEFAULT_INTERVALS)
    return [int(x) for x in intervals]


def _tomorrow_start() -> int:
    """Unix timestamp for the start of tomorrow (local midnight)."""
    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int(tomorrow.timestamp())


def compute_next(
    *, current_step: int, ease_factor: float, status: Status,
    last_reviewed_at: Optional[int] = None,
) -> tuple[int, int, float]:
    """Return (new_step, next_review_at_unix, new_ease_factor).

    last_reviewed_at: unix timestamp of the previous review. When provided,
    "remembered" uses Anki-style logic: the next interval is at least as long
    as the actual elapsed time multiplied by the ease factor, rewarding memory
    that outlasted its scheduled window.
    """
    intervals = get_intervals()
    ef = ease_factor or DEFAULT_EASE
    step = max(0, int(current_step))
    now = int(time.time())

    if status == "remembered":
        new_step = min(step + 1, len(intervals) - 1)
        new_ef = min(ef + EASE_BONUS, EASE_MAX)
        step_days = intervals[new_step] * (new_ef / DEFAULT_EASE)
        if last_reviewed_at:
            actual_elapsed_days = (now - last_reviewed_at) / 86400
            anki_days = actual_elapsed_days * (new_ef / DEFAULT_EASE)
            days = max(step_days, anki_days)
        else:
            days = step_days
    elif status == "fuzzy":
        new_step = step
        new_ef = ef
        days = intervals[new_step] * (new_ef / DEFAULT_EASE)
    elif status == "forgot":
        new_step = 0
        new_ef = max(ef - EASE_PENALTY, EASE_MIN)
        days = intervals[0] * (new_ef / DEFAULT_EASE)
    else:
        raise ValueError(f"unknown review status: {status!r}")

    next_at = now + int(days * 86400)

    # "forgot" must never land within the current day — prevent same-session reappearance.
    # This also fixes the low-ease edge case where intervals[0] * (ease/2.5) < 24h.
    if status == "forgot":
        next_at = max(next_at, _tomorrow_start())

    return new_step, next_at, new_ef


def initial_next_review(first_solved_at: int) -> int:
    """First scheduled review is `intervals[0]` days after first solve."""
    intervals = get_intervals()
    return int(first_solved_at) + intervals[0] * 86400
