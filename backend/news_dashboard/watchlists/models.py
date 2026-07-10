"""Request models for the watchlists domain."""

from __future__ import annotations

from pydantic import BaseModel


class WatchlistCreateRequest(BaseModel):
    label: str
    query: str
    threshold: float = 0.5
    enabled: bool = True
    notify_push: bool = True


class WatchlistUpdateRequest(BaseModel):
    label: str | None = None
    query: str | None = None
    threshold: float | None = None
    enabled: bool | None = None
    notify_push: bool | None = None


class WatchlistPreviewRequest(BaseModel):
    query: str
    threshold: float = 0.5
