"""Tests for web.dev Blog default source (issue #772)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest import sync_sources
from news_dashboard.sources import DEFAULT_SOURCES

# Unit tests (no DB)


def test_web_dev_blog_in_default_sources() -> None:
    """web-dev-blog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "web-dev-blog" in by_slug, f"web-dev-blog not found; slugs: {sorted(by_slug)[:10]}..."


def test_web_dev_blog_metadata() -> None:
    """web-dev-blog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "web-dev-blog")
    assert src.name == "web.dev Blog"
    assert src.url == "https://web.dev/feed.xml"
    assert src.category == "web"
    assert src.kind == "rss_feed"
    assert src.priority == 70
    assert src.enabled is True
    assert src.lang == "en"


def test_web_dev_blog_interest_tags() -> None:
    """web-dev-blog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "web-dev-blog")
    assert "web" in src.interest_tags
    assert "frontend" in src.interest_tags
    assert "performance" in src.interest_tags


def test_web_dev_blog_routes_to_rss_feed() -> None:
    """web-dev-blog kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "web-dev-blog")
    assert src.kind == "rss_feed"


# Integration tests (PostgreSQL)


def test_web_dev_blog_sync_persists_row(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_sources() creates a sources row for web-dev-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'web-dev-blog'"
        ).fetchone()

    assert row is not None, "web-dev-blog row missing from sources table"
    assert row["slug"] == "web-dev-blog"
    assert row["name"] == "web.dev Blog"
    assert row["url"] == "https://web.dev/feed.xml"
    assert row["category"] == "web"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 70
    assert row["enabled"] is True


def test_web_dev_blog_sync_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running sync_sources twice does not duplicate web-dev-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'web-dev-blog'"
        ).fetchone()["c"]

    assert count == 1
