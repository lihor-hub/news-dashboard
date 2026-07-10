"""Request models for the tags routes domain."""

from __future__ import annotations

from pydantic import BaseModel


class TagCreateRequest(BaseModel):
    name: str
    color: str | None = None


class TagRenameRequest(BaseModel):
    name: str


class ArticleTagRequest(BaseModel):
    tag_id: int
