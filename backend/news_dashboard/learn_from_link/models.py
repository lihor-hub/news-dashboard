"""Request and structured-content models for Learn from Link lessons."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LessonCreateRequest(BaseModel):
    url: str


LessonVerdict = Literal["skip", "skim", "read", "study"]


class LessonCitation(BaseModel):
    """A claim-supporting snippet, checked against the source content before saving."""

    text: str = Field(min_length=1)
    note: str | None = None


class LessonContent(BaseModel):
    """AI-generated structured lesson, validated before a lesson is marked complete."""

    gist: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    key_claims: list[str] = Field(min_length=1)
    prerequisites: list[str] = Field(default_factory=list)
    why_it_matters: str = Field(min_length=1)
    verdict: LessonVerdict
    verdict_rationale: str = Field(min_length=1)
    intended_readers: list[str] = Field(default_factory=list)
    guiding_questions: list[str] = Field(default_factory=list)
    citations: list[LessonCitation] = Field(default_factory=list)
