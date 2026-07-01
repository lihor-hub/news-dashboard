"""Tests for Google DeepMind Blog default source (issue #746)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest import sync_sources
from news_dashboard.sources import DEFAULT_SOURCES

# ── Unit tests (no DB) ───────────────────────────────────────────────────


def test_deepmind_blog_in_default_sources() -> None:
    """deepmind-blog SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "deepmind-blog" in by_slug, f"deepmind-blog not found; slugs: {sorted(by_slug)[:10]}..."


def test_deepmind_blog_metadata() -> None:
    """deepmind-blog has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "deepmind-blog")
    assert src.name == "Google DeepMind Blog"
    assert src.url == "https://deepmind.google/blog/"
    assert src.category == "ai-llm"
    assert src.kind == "scraped_page"
    assert src.priority == 85
    assert src.enabled is True
    assert src.lang == "en"


def test_deepmind_blog_interest_tags() -> None:
    """deepmind-blog carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "deepmind-blog")
    assert "agents" in src.interest_tags
    assert "model-releases" in src.interest_tags
    assert "evals" in src.interest_tags
    assert "product-news" in src.interest_tags


def test_deepmind_blog_routes_to_scraped_page() -> None:
    """deepmind-blog kind is scraped_page, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "deepmind-blog")
    assert src.kind == "scraped_page"


# ── Integration tests (PostgreSQL) ────────────────────────────────────────


def test_deepmind_blog_sync_persists_row(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_sources() creates a sources row for deepmind-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'deepmind-blog'"
        ).fetchone()

    assert row is not None, "deepmind-blog row missing from sources table"
    assert row["slug"] == "deepmind-blog"
    assert row["name"] == "Google DeepMind Blog"
    assert row["url"] == "https://deepmind.google/blog/"
    assert row["category"] == "ai-llm"
    assert row["kind"] == "scraped_page"
    assert row["priority"] == 85
    assert row["enabled"] is True


def test_deepmind_blog_sync_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running sync_sources twice does not duplicate deepmind-blog."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'deepmind-blog'"
        ).fetchone()["c"]

    assert count == 1
