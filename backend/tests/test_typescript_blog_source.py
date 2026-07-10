"""Tests for TypeScript Blog default source (issue #770)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest.service import sync_sources
from news_dashboard.sources.service import DEFAULT_SOURCES

# Unit tests (no DB)


def test_typescript_blog_in_default_sources() -> None:
    """typescript-blog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "typescript-blog" in by_slug, (
        f"typescript-blog not found; slugs: {sorted(by_slug)[:10]}..."
    )


def test_typescript_blog_metadata() -> None:
    """typescript-blog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "typescript-blog")
    assert src.name == "TypeScript Blog"
    assert src.url == "https://devblogs.microsoft.com/typescript/feed/"
    assert src.category == "developer-tools"
    assert src.kind == "rss_feed"
    assert src.priority == 78
    assert src.enabled is True
    assert src.lang == "en"


def test_typescript_blog_interest_tags() -> None:
    """typescript-blog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "typescript-blog")
    assert "programming" in src.interest_tags
    assert "frontend" in src.interest_tags
    assert "software-development" in src.interest_tags


def test_typescript_blog_routes_to_rss_feed() -> None:
    """typescript-blog kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "typescript-blog")
    assert src.kind == "rss_feed"


# Integration tests (PostgreSQL)


def test_typescript_blog_sync_persists_row(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_sources() creates a sources row for typescript-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'typescript-blog'"
        ).fetchone()

    assert row is not None, "typescript-blog row missing from sources table"
    assert row["slug"] == "typescript-blog"
    assert row["name"] == "TypeScript Blog"
    assert row["url"] == "https://devblogs.microsoft.com/typescript/feed/"
    assert row["category"] == "developer-tools"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 78
    assert row["enabled"] is True


def test_typescript_blog_sync_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running sync_sources twice does not duplicate typescript-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'typescript-blog'"
        ).fetchone()["c"]

    assert count == 1
