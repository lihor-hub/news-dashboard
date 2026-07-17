"""Request models for the user settings domain."""

from __future__ import annotations

from pydantic import BaseModel


class NotificationSettingsUpdate(BaseModel):
    briefing_time: str | None = None
    push_enabled: bool | None = None
    email_enabled: bool | None = None
    briefing_timezone: str | None = None
    recap_enabled: bool | None = None
    recap_day: str | None = None
    briefing_include_reading_list: bool | None = None
    briefing_reading_list_limit: int | None = None


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class PushUnsubscribeRequest(BaseModel):
    endpoint: str | None = None


class RecommendationPreferencesUpdate(BaseModel):
    category_weights: dict[str, float] | None = None
    novelty_weight: float | None = None


class DeleteAccountRequest(BaseModel):
    confirmation: str


class AnalyticsSettingsUpdate(BaseModel):
    enabled: bool
