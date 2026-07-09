"""Request models for Learn from Link lessons."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
GistText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=280)]


class LessonCreateRequest(BaseModel):
    url: str


class LessonCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: NonEmptyText
    snippet: NonEmptyText
    source: NonEmptyText


class ReadWorthiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["skip", "skim", "read", "study"]
    rationale: NonEmptyText


class LessonDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gist: GistText
    explanation: NonEmptyText
    key_claims: list[NonEmptyText] = Field(min_length=1)
    prerequisite_concepts: list[NonEmptyText] = Field(min_length=1)
    why_it_matters: NonEmptyText
    read_worthiness: ReadWorthiness
    who_should_read: list[NonEmptyText] = Field(min_length=1)
    questions_to_keep_in_mind: list[NonEmptyText] = Field(min_length=1)
    citations: list[LessonCitation] = Field(min_length=1)
