from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    memory_type: str = Field(default="preference", max_length=40)
    source: str = Field(default="explicit", max_length=40)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class MemoryUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=500)
    memory_type: str | None = Field(default=None, max_length=40)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    active: bool | None = None
