"""Tests for Trail of Bits Blog default source (issue #768)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest import sync_sources
from news_dashboard.sources import DEFAULT_SOURCES

# ── Unit tests (no DB) ───────────────────────────────────────────────────


def test_trail_of_bits_blog_in_default_sources() -> None:
    """trail-of-bits-blog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "trail-of-bits-blog" in by_slug, f"trail-of-bits-blog not found; slugs: {sorted(by_slug)[:10]}..."


def test_trail_of_bits_blog_metadata() -> None:
    """trail-of-bits-blog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "trail-of-bits-blog")
    assert src.name == "Trail of Bits Blog"
    assert src.url == "https://blog.trailofbits.com/feed/"
    assert src.category == "security"
    assert src.kind == "rss_feed"
    assert src.priority == 76
    assert src.enabled is True
    assert src.lang == "en"


def test_trail_of_bits_blog_interest_tags() -> None:
    """trail-of-bits-blog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "trail-of-bits-blog")
    assert "security" in src.interest_tags
    assert "infra" in src.interest_tags
    assert "software-development" in src.interest_tags


def test_trail_of_bits_blog_routes_to_rss_feed() -> None:
    """trail-of-bits-blog kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "trail-of-bits-blog")
    assert src.kind == "rss_feed"


# ── Integration tests (PostgreSQL) ────────────────────────────────────────


def test_trail_of_bits_blog_sync_persists_row(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_sources() creates a sources row for trail-of-bits-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'trail-of-bits-blog'"
        ).fetchone()

    assert row is not None, "trail-of-bits-blog row missing from sources table"
    assert row["slug"] == "trail-of-bits-blog"
    assert row["name"] == "Trail of Bits Blog"
    assert row["url"] == "https://blog.trailofbits.com/feed/"
    assert row["category"] == "security"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 76
    assert row["enabled"] is True


def test_trail_of_bits_blog_sync_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running sync_sources twice does not duplicate trail-of-bits-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'trail-of-bits-blog'"
        ).fetchone()["c"]

    assert count == 1