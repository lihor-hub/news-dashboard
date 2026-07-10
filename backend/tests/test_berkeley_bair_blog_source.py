"""Tests for Berkeley BAIR Blog default source (issue #765)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from news_dashboard.ingest.service import _fetch_feed_entries, sync_sources
from news_dashboard.sources.service import DEFAULT_SOURCES


def test_berkeley_bair_blog_in_default_sources() -> None:
    """berkeley-bair-blog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "berkeley-bair-blog" in by_slug, (
        f"berkeley-bair-blog not found; slugs: {sorted(by_slug)[:10]}..."
    )


def test_berkeley_bair_blog_metadata() -> None:
    """berkeley-bair-blog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "berkeley-bair-blog")
    assert src.name == "Berkeley BAIR Blog"
    assert src.url == "https://bair.berkeley.edu/blog/feed.xml"
    assert src.category == "ai-research"
    assert src.kind == "rss_feed"
    assert src.priority == 74
    assert src.enabled is True
    assert src.lang == "en"


def test_berkeley_bair_blog_interest_tags_match_onboarding() -> None:
    """berkeley-bair-blog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "berkeley-bair-blog")
    assert src.interest_tags == ("evals", "model-releases", "research")


def test_berkeley_bair_blog_routes_to_rss_feed() -> None:
    """berkeley-bair-blog kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "berkeley-bair-blog")
    assert src.kind == "rss_feed"


def test_berkeley_bair_blog_feed_parse_uses_configured_url() -> None:
    """berkeley-bair-blog can be parsed through the standard RSS feed path."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "berkeley-bair-blog")
    with patch("news_dashboard.ingest.service._parse_feed_url") as parse_feed:
        parse_feed.return_value = [{"url": "https://bair.berkeley.edu/blog/example/"}]

        assert _fetch_feed_entries(src) == [{"url": "https://bair.berkeley.edu/blog/example/"}]

    parse_feed.assert_called_once_with("https://bair.berkeley.edu/blog/feed.xml")


def test_berkeley_bair_blog_sync_persists_row(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_sources() creates a sources row for berkeley-bair-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'berkeley-bair-blog'"
        ).fetchone()

    assert row is not None, "berkeley-bair-blog row missing from sources table"
    assert row["slug"] == "berkeley-bair-blog"
    assert row["name"] == "Berkeley BAIR Blog"
    assert row["url"] == "https://bair.berkeley.edu/blog/feed.xml"
    assert row["category"] == "ai-research"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 74
    assert row["enabled"] is True


def test_berkeley_bair_blog_sync_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running sync_sources twice does not duplicate berkeley-bair-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'berkeley-bair-blog'"
        ).fetchone()["c"]

    assert count == 1
