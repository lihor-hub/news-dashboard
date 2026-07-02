"""Request models for the quizzes feature module."""

from __future__ import annotations

from pydantic import BaseModel


class GoalCreateRequest(BaseModel):
    description: str
    keywords: str = ""


class QuizSubmitRequest(BaseModel):
    answers: list[int]
