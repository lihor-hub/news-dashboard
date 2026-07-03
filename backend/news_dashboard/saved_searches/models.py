"""Request models for reusable saved search views."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SavedSearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = ""
    states: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    starred_only: bool = False
    include_archived: bool = False
    date_range: str = "all"
    tag_id: int | None = None


class SavedSearchCreateRequest(BaseModel):
    name: str
    filters: SavedSearchFilters


class SavedSearchUpdateRequest(BaseModel):
    name: str | None = None
    filters: SavedSearchFilters | None = None
