"""Request models for the reading list API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ReadingListAddRequest(BaseModel):
    url: str
    note: str | None = None


class ReadingListUpdateRequest(BaseModel):
    status: Literal["unread", "done", "archived"] | None = None
    note: str | None = None


class ReadingListReorderRequest(BaseModel):
    ordered_ids: list[int]
