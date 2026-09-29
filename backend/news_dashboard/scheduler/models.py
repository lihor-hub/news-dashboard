"""Request models for the scheduler domain."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IntervalUpdate(BaseModel):
    minutes: int


class RetentionPolicyUpdate(BaseModel):
    days: int | None = Field(default=None, ge=1)
