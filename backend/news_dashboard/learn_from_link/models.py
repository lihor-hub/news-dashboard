"""Request models for Learn from Link lessons."""

from __future__ import annotations

from pydantic import BaseModel


class LessonCreateRequest(BaseModel):
    url: str
