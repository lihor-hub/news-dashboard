"""Request models for the ai_feedback feature module."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

SubjectType = Literal["briefing", "recommendation"]
Verdict = Literal[-1, 1]


class AiFeedbackRequest(BaseModel):
    subject_type: SubjectType
    subject_id: int
    article_id: int | None = None
    verdict: Verdict
    comment: str | None = None
