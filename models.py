"""Pydantic v2 request models for the JSON API."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Difficulty = Literal["easy", "medium", "hard"]
ReviewStatus = Literal["remembered", "fuzzy", "forgot"]


class ProblemCreate(BaseModel):
    lc_number: int = Field(..., ge=1)
    title: str
    difficulty: Difficulty
    tags: list[str] = []
    notes: str = ""                   # 其他备注（可选 Markdown）
    first_solved_at: Optional[int] = None
    approach_clear: bool = True       # 思路是否清晰
    approach_desc: str = ""           # approach_clear=False 时填的做法描述
    syntax_errors: str = ""           # 语法错误 / 语法要点
    style_issues: str = ""            # 写法优化


class ProblemUpdate(BaseModel):
    title: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    first_solved_at: Optional[int] = None
    ai_summary: Optional[Any] = None
    approach_clear: Optional[bool] = None
    approach_desc: Optional[str] = None
    syntax_errors: Optional[str] = None
    style_issues: Optional[str] = None


class ReviewMark(BaseModel):
    status: ReviewStatus


class IntervalsUpdate(BaseModel):
    intervals: list[int] = Field(..., min_length=1)


class CardUpdate(BaseModel):
    question: Optional[str] = None
    hint: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
