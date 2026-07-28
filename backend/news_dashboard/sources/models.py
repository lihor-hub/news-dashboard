"""Request models for the sources domain."""

from __future__ import annotations

import re

from fastapi import (
    HTTPException,
)
from pydantic import BaseModel

USER_CREATED_SOURCE_KINDS = frozenset({"rss_feed", "reddit_feed", "lobsters_feed", "mastodon_feed"})


class EnabledUpdate(BaseModel):
    enabled: bool


class HighPriorityUpdate(BaseModel):
    high_priority: bool


class CreateSourceRequest(BaseModel):
    url: str
    name: str
    category: str = "tech"
    slug: str | None = None
    kind: str = "rss_feed"
    high_priority: bool = True
    provider: str | None = None

    def validate_kind(self) -> None:
        if self.kind in USER_CREATED_SOURCE_KINDS:
            return
        allowed = ", ".join(sorted(USER_CREATED_SOURCE_KINDS))
        raise HTTPException(
            status_code=400,
            detail=f"unsupported source kind '{self.kind}'. Supported kinds: {allowed}",
        )

    def validated_slug(self, name: str) -> str:
        """Return a non-empty slug, normalised from name if not provided."""

        raw = self.slug or re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
        slug = re.sub(r"-{2,}", "-", raw).strip("-")[:80]
        if not slug:
            raise HTTPException(status_code=400, detail="slug must not be empty")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*[a-z0-9]|[a-z0-9]", slug):
            raise HTTPException(
                status_code=400,
                detail="slug must contain only lowercase letters, digits, and hyphens",
            )
        return slug


class PreviewSourceRequest(BaseModel):
    url: str
    kind: str = "rss_feed"

    def validate_kind(self) -> None:
        if self.kind in USER_CREATED_SOURCE_KINDS:
            return
        allowed = ", ".join(sorted(USER_CREATED_SOURCE_KINDS))
        raise HTTPException(
            status_code=400,
            detail=f"unsupported source kind '{self.kind}'. Supported kinds: {allowed}",
        )


class SubstackPreviewRequest(BaseModel):
    url: str


class SourceCleanupRequest(BaseModel):
    source_slugs: list[str]
