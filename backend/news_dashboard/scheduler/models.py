"""Request models for the scheduler domain."""

from __future__ import annotations

from pydantic import BaseModel


class IntervalUpdate(BaseModel):
    minutes: int
