"""Tests for Cloudflare Blog default source (issue #751)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest.service import sync_sources
from news_dashboard.sources.service import DEFAULT_SOURCES

# ── Unit tests (no DB) ───────────────────────────────────────────────────


def test_cloudflare_blog_in_default_sources() -> None:
    """cloudflare-blog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "cloudflare-blog" in by_slug, (
        f"cloudflare-blog not found; slugs: {sorted(by_slug)[:10]}..."
    )


def test_cloudflare_blog_metadata() -> None:
    """cloudflare-blog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "cloudflare-blog")
    assert src.name == "Cloudflare Blog"
    assert src.url == "https://blog.cloudflare.com/rss/"
    assert src.category == "cloud-infra"
    assert src.kind == "rss_feed"
    assert src.priority == 70
    assert src.enabled is True
    assert src.lang == "en"


def test_cloudflare_blog_interest_tags() -> None:
    """cloudflare-blog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "cloudflare-blog")
    assert "cloud" in src.interest_tags
    assert "infra" in src.interest_tags
    assert "security" in src.interest_tags


def test_cloudflare_blog_routes_to_rss_feed() -> None:
    """cloudflare-blog kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "cloudflare-blog")
    assert src.kind == "rss_feed"


# ── Integration tests (PostgreSQL) ────────────────────────────────────────


def test_cloudflare_blog_sync_persists_row(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sync_sources() creates a sources row for cloudflare-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'cloudflare-blog'"
        ).fetchone()

    assert row is not None, "cloudflare-blog row missing from sources table"
    assert row["slug"] == "cloudflare-blog"
    assert row["name"] == "Cloudflare Blog"
    assert row["url"] == "https://blog.cloudflare.com/rss/"
    assert row["category"] == "cloud-infra"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 70
    assert row["enabled"] is True


def test_cloudflare_blog_sync_idempotent(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running sync_sources twice does not duplicate cloudflare-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'cloudflare-blog'"
        ).fetchone()["c"]

    assert count == 1
