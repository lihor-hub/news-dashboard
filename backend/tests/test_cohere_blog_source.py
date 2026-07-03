"""Tests for Cohere Blog default source (issue #749)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest import sync_sources
from news_dashboard.sources import DEFAULT_SOURCES

# ── Unit tests (no DB) ───────────────────────────────────────────────────


def test_cohere_blog_in_default_sources() -> None:
    """cohere-blog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "cohere-blog" in by_slug, f"cohere-blog not found; slugs: {sorted(by_slug)[:10]}..."


def test_cohere_blog_metadata() -> None:
    """cohere-blog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "cohere-blog")
    assert src.name == "Cohere Blog"
    assert src.url == "https://cohere.com/blog"
    assert src.category == "ai-llm"
    assert src.kind == "scraped_page"
    assert src.priority == 75
    assert src.enabled is True
    assert src.lang == "en"


def test_cohere_blog_interest_tags() -> None:
    """cohere-blog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "cohere-blog")
    assert "agents" in src.interest_tags
    assert "model-releases" in src.interest_tags
    assert "infra" in src.interest_tags
    assert "product-news" in src.interest_tags


def test_cohere_blog_routes_to_scraped_page() -> None:
    """cohere-blog kind is scraped_page, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "cohere-blog")
    assert src.kind == "scraped_page"


# ── Integration tests (PostgreSQL) ────────────────────────────────────────


def test_cohere_blog_sync_persists_row(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_sources() creates a sources row for cohere-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'cohere-blog'"
        ).fetchone()

    assert row is not None, "cohere-blog row missing from sources table"
    assert row["slug"] == "cohere-blog"
    assert row["name"] == "Cohere Blog"
    assert row["url"] == "https://cohere.com/blog"
    assert row["category"] == "ai-llm"
    assert row["kind"] == "scraped_page"
    assert row["priority"] == 75
    assert row["enabled"] is True


def test_cohere_blog_sync_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running sync_sources twice does not duplicate cohere-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'cohere-blog'"
        ).fetchone()["c"]

    assert count == 1
