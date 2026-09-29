"""Request models for the scheduler domain."""

from __future__ import annotations

from pydantic import BaseModel, Field, StrictInt

from news_dashboard.scheduler.retention import MAX_RETENTION_DAYS


class IntervalUpdate(BaseModel):
    minutes: int


class RetentionPolicyUpdate(BaseModel):
    days: StrictInt | None = Field(default=None, ge=1, le=MAX_RETENTION_DAYS)
