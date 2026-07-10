"""Request models for the events domain."""

from __future__ import annotations

from pydantic import BaseModel, Field

from news_dashboard.analytics import (
    MAX_EVENTS_PER_BATCH,
)


class AnalyticsEvent(BaseModel):
    type: str
    route: str | None = None
    article_id: int | None = None
    feature: str | None = None
    duration_ms: int | None = None


class AnalyticsEventsRequest(BaseModel):
    events: list[AnalyticsEvent] = Field(max_length=MAX_EVENTS_PER_BATCH)
