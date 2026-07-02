"""Response models for reading streaks and achievements."""

from __future__ import annotations

from pydantic import BaseModel


class ReadingStreakResponse(BaseModel):
    current_streak_days: int
    longest_streak_days: int
    last_active_date: str | None
    active_days: list[str]
    qualifying_activity: str


class AchievementResponse(BaseModel):
    key: str
    title: str
    description: str
    unlocked: bool
    unlocked_at: str | None = None
    progress: int
    target: int


class AchievementsResponse(BaseModel):
    items: list[AchievementResponse]
