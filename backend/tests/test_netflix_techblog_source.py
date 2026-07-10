"""Tests for Netflix TechBlog default source (issue #766)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest.service import sync_sources
from news_dashboard.sources.service import DEFAULT_SOURCES

# Unit tests (no DB)


def test_netflix_techblog_in_default_sources() -> None:
    """netflix-techblog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "netflix-techblog" in by_slug, (
        f"netflix-techblog not found; slugs: {sorted(by_slug)[:10]}..."
    )


def test_netflix_techblog_metadata() -> None:
    """netflix-techblog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "netflix-techblog")
    assert src.name == "Netflix TechBlog"
    assert src.url == "https://netflixtechblog.com/feed"
    assert src.category == "engineering"
    assert src.kind == "rss_feed"
    assert src.priority == 68
    assert src.enabled is True
    assert src.lang == "en"


def test_netflix_techblog_interest_tags() -> None:
    """netflix-techblog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "netflix-techblog")
    assert "infra" in src.interest_tags
    assert "software-development" in src.interest_tags
    assert "cloud" in src.interest_tags


def test_netflix_techblog_routes_to_rss_feed() -> None:
    """netflix-techblog kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "netflix-techblog")
    assert src.kind == "rss_feed"


# Integration tests (PostgreSQL)


def test_netflix_techblog_sync_persists_row(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_sources() creates a sources row for netflix-techblog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'netflix-techblog'"
        ).fetchone()

    assert row is not None, "netflix-techblog row missing from sources table"
    assert row["slug"] == "netflix-techblog"
    assert row["name"] == "Netflix TechBlog"
    assert row["url"] == "https://netflixtechblog.com/feed"
    assert row["category"] == "engineering"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 68
    assert row["enabled"] is True


def test_netflix_techblog_sync_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running sync_sources twice does not duplicate netflix-techblog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'netflix-techblog'"
        ).fetchone()["c"]

    assert count == 1
