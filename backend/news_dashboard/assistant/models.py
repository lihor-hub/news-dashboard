"""Request models for the assistant domain."""

from __future__ import annotations

from pydantic import BaseModel, Field

MAX_ASK_QUERY_LENGTH = 2_000


class AskRequest(BaseModel):
    query: str = Field(max_length=MAX_ASK_QUERY_LENGTH)
    include_all: bool = False
    session_id: str | None = Field(default=None, max_length=199)


class AgentActionPlanRequest(BaseModel):
    query: str = Field(max_length=MAX_ASK_QUERY_LENGTH)


class FeedbackRequest(BaseModel):
    trace_id: str
    helpful: bool
    comment: str | None = None
