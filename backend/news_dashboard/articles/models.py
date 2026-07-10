"""Request models for the articles domain."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class StatusUpdate(BaseModel):
    status: str


class StateUpdate(BaseModel):
    state: str


class StarUpdate(BaseModel):
    starred: bool


class LaterUpdate(BaseModel):
    days: int = 1


class SaveSharedUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2_000)
    title: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=4_000)

    @field_validator("url")
    @classmethod
    def _url_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            message = "url must not be blank"
            raise ValueError(message)
        return stripped

    @field_validator("title", "text")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None
