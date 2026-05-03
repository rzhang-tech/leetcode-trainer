"""Spaced-repetition scheduler (Ebbinghaus-flavoured).

State carried per problem:
  review_step  -- index into the configured intervals list
  ease_factor  -- multiplier on the base interval (clamped to [1.3, 3.0])

Transitions on a review:
  remembered -> step += 1 (capped at last index), ease += 0.05
  fuzzy      -> step unchanged, ease unchanged
  forgot     -> step = 0,                          ease -= 0.2

The actual delay used is `intervals[new_step] * (ease / 2.5)` days, so a high
ease factor stretches you out and a low one keeps you closer to the base curve.
"""
from __future__ import annotations

import time
from typing import Literal

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


def compute_next(
    *, current_step: int, ease_factor: float, status: Status
) -> tuple[int, int, float]:
    """Return (new_step, next_review_at_unix, new_ease_factor)."""
    intervals = get_intervals()
    ef = ease_factor or DEFAULT_EASE
    step = max(0, int(current_step))

    if status == "remembered":
        new_step = min(step + 1, len(intervals) - 1)
        new_ef = min(ef + EASE_BONUS, EASE_MAX)
    elif status == "fuzzy":
        new_step = step
        new_ef = ef
    elif status == "forgot":
        new_step = 0
        new_ef = max(ef - EASE_PENALTY, EASE_MIN)
    else:
        raise ValueError(f"unknown review status: {status!r}")

    base_days = intervals[new_step]
    days = base_days * (new_ef / DEFAULT_EASE)
    delta = int(days * 86400)
    return new_step, int(time.time()) + delta, new_ef


def initial_next_review(first_solved_at: int) -> int:
    """First scheduled review is `intervals[0]` days after first solve."""
    intervals = get_intervals()
    return int(first_solved_at) + intervals[0] * 86400
