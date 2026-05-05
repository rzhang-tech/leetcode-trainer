"""Pydantic v2 request models for the JSON API."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field

Difficulty = Literal["easy", "medium", "hard"]
ReviewStatus = Literal["remembered", "fuzzy", "forgot"]


class ProblemCreate(BaseModel):
    lc_number: int = Field(..., ge=1)
    title: str
    difficulty: Difficulty
    tags: list[str] = []
    notes: str = ""
    first_solved_at: Optional[int] = None
    approach_clear: bool = True
    approach_desc: str = ""
    syntax_errors: str = ""
    style_issues: str = ""


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


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str
