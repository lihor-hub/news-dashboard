"""Tests for Meta AI Blog default source (issue #747)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest import sync_sources
from news_dashboard.sources import DEFAULT_SOURCES

# ── Unit tests (no DB) ───────────────────────────────────────────────────


def test_meta_ai_blog_in_default_sources() -> None:
    """meta-ai-blog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "meta-ai-blog" in by_slug, f"meta-ai-blog not found; slugs: {sorted(by_slug)[:10]}..."


def test_meta_ai_blog_metadata() -> None:
    """meta-ai-blog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "meta-ai-blog")
    assert src.name == "Meta AI Blog"
    assert src.url == "https://ai.meta.com/blog/"
    assert src.category == "ai-llm"
    assert src.kind == "scraped_page"
    assert src.priority == 80
    assert src.enabled is True
    assert src.lang == "en"


def test_meta_ai_blog_interest_tags() -> None:
    """meta-ai-blog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "meta-ai-blog")
    assert "model-releases" in src.interest_tags
    assert "evals" in src.interest_tags
    assert "infra" in src.interest_tags
    assert "product-news" in src.interest_tags


def test_meta_ai_blog_routes_to_scraped_page() -> None:
    """meta-ai-blog kind is scraped_page, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "meta-ai-blog")
    assert src.kind == "scraped_page"


# ── Integration tests (PostgreSQL) ────────────────────────────────────────


def test_meta_ai_blog_sync_persists_row(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_sources() creates a sources row for meta-ai-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'meta-ai-blog'"
        ).fetchone()

    assert row is not None, "meta-ai-blog row missing from sources table"
    assert row["slug"] == "meta-ai-blog"
    assert row["name"] == "Meta AI Blog"
    assert row["url"] == "https://ai.meta.com/blog/"
    assert row["category"] == "ai-llm"
    assert row["kind"] == "scraped_page"
    assert row["priority"] == 80
    assert row["enabled"] is True


def test_meta_ai_blog_sync_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running sync_sources twice does not duplicate meta-ai-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'meta-ai-blog'"
        ).fetchone()["c"]

    assert count == 1
