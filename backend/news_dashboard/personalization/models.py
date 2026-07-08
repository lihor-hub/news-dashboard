"""Request models for personalization endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class NudgeActionRequest(BaseModel):
    nudge_id: str


class NudgeDismissRequest(BaseModel):
    nudge_id: str
    cooldown_days: int = 7
