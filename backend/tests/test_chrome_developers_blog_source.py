"""Tests for Chrome Developers Blog default source (issue #773)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest import sync_sources
from news_dashboard.sources import DEFAULT_SOURCES

# ── Unit tests (no DB) ───────────────────────────────────────────────────


def test_chrome_developers_blog_in_default_sources() -> None:
    """chrome-developers-blog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "chrome-developers-blog" in by_slug, (
        f"chrome-developers-blog not found; slugs: {sorted(by_slug)[:10]}..."
    )


def test_chrome_developers_blog_metadata() -> None:
    """chrome-developers-blog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "chrome-developers-blog")
    assert src.name == "Chrome Developers Blog"
    assert src.url == "https://developer.chrome.com/static/blog/feed.xml"
    assert src.category == "web"
    assert src.kind == "rss_feed"
    assert src.priority == 70
    assert src.enabled is True
    assert src.lang == "en"


def test_chrome_developers_blog_interest_tags() -> None:
    """chrome-developers-blog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "chrome-developers-blog")
    assert "web" in src.interest_tags
    assert "frontend" in src.interest_tags
    assert "product-news" in src.interest_tags


def test_chrome_developers_blog_routes_to_rss_feed() -> None:
    """chrome-developers-blog kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "chrome-developers-blog")
    assert src.kind == "rss_feed"


# ── Integration tests (PostgreSQL) ────────────────────────────────────────


def test_chrome_developers_blog_sync_persists_row(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sync_sources() creates a sources row for chrome-developers-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'chrome-developers-blog'"
        ).fetchone()

    assert row is not None, "chrome-developers-blog row missing from sources table"
    assert row["slug"] == "chrome-developers-blog"
    assert row["name"] == "Chrome Developers Blog"
    assert row["url"] == "https://developer.chrome.com/static/blog/feed.xml"
    assert row["category"] == "web"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 70
    assert row["enabled"] is True


def test_chrome_developers_blog_sync_idempotent(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running sync_sources twice does not duplicate chrome-developers-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'chrome-developers-blog'"
        ).fetchone()["c"]

    assert count == 1
