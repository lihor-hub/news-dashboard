"""Request models for the assistant domain."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_ASK_QUERY_LENGTH = 2_000


class AskRequest(BaseModel):
    query: str = Field(max_length=MAX_ASK_QUERY_LENGTH)
    include_all: bool = False
    session_id: str | None = None

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        if len(value) > 199 or not value.isascii():
            message = "session_id must be an ASCII string of at most 199 characters"
            raise ValueError(message)
        return value


class AgentActionPlanRequest(BaseModel):
    query: str = Field(max_length=MAX_ASK_QUERY_LENGTH)


class FeedbackRequest(BaseModel):
    trace_id: str
    helpful: bool
    comment: str | None = None
