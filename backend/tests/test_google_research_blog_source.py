"""Tests for Google Research Blog default source (issue #764)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest.service import sync_sources
from news_dashboard.sources.service import DEFAULT_SOURCES

# ── Unit tests (no DB) ───────────────────────────────────────────────────


def test_google_research_blog_in_default_sources() -> None:
    """google-research-blog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "google-research-blog" in by_slug, (
        f"google-research-blog not found; slugs: {sorted(by_slug)[:10]}..."
    )


def test_google_research_blog_metadata() -> None:
    """google-research-blog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "google-research-blog")
    assert src.name == "Google Research Blog"
    assert src.url == "https://research.google/blog/rss/"
    assert src.category == "ai-research"
    assert src.kind == "rss_feed"
    assert src.priority == 78
    assert src.enabled is True
    assert src.lang == "en"


def test_google_research_blog_interest_tags() -> None:
    """google-research-blog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "google-research-blog")
    assert "evals" in src.interest_tags
    assert "model-releases" in src.interest_tags
    assert "research" in src.interest_tags
    assert "security" in src.interest_tags


def test_google_research_blog_routes_to_rss_feed() -> None:
    """google-research-blog kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "google-research-blog")
    assert src.kind == "rss_feed"


# ── Integration tests (PostgreSQL) ────────────────────────────────────────


def test_google_research_blog_sync_persists_row(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_sources() creates a sources row for google-research-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'google-research-blog'"
        ).fetchone()

    assert row is not None, "google-research-blog row missing from sources table"
    assert row["slug"] == "google-research-blog"
    assert row["name"] == "Google Research Blog"
    assert row["url"] == "https://research.google/blog/rss/"
    assert row["category"] == "ai-research"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 78
    assert row["enabled"] is True


def test_google_research_blog_sync_idempotent(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running sync_sources twice does not duplicate google-research-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'google-research-blog'"
        ).fetchone()["c"]

    assert count == 1
