"""Tests for Mistral AI News default source (issue #748)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest import sync_sources
from news_dashboard.sources import DEFAULT_SOURCES

# ── Unit tests (no DB) ───────────────────────────────────────────────────


def test_mistral_ai_news_in_default_sources() -> None:
    """mistral-ai-news SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "mistral-ai-news" in by_slug, (
        f"mistral-ai-news not found; slugs: {sorted(by_slug)[:10]}..."
    )


def test_mistral_ai_news_metadata() -> None:
    """mistral-ai-news has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "mistral-ai-news")
    assert src.name == "Mistral AI News"
    assert src.url == "https://mistral.ai/news/"
    assert src.category == "ai-llm"
    assert src.kind == "scraped_page"
    assert src.priority == 80
    assert src.enabled is True
    assert src.lang == "en"


def test_mistral_ai_news_interest_tags() -> None:
    """mistral-ai-news carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "mistral-ai-news")
    assert "agents" in src.interest_tags
    assert "model-releases" in src.interest_tags
    assert "product-news" in src.interest_tags


def test_mistral_ai_news_routes_to_scraped_page() -> None:
    """mistral-ai-news kind is scraped_page, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "mistral-ai-news")
    assert src.kind == "scraped_page"


# ── Integration tests (PostgreSQL) ────────────────────────────────────────


def test_mistral_ai_news_sync_persists_row(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_sources() creates a sources row for mistral-ai-news."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'mistral-ai-news'"
        ).fetchone()

    assert row is not None, "mistral-ai-news row missing from sources table"
    assert row["slug"] == "mistral-ai-news"
    assert row["name"] == "Mistral AI News"
    assert row["url"] == "https://mistral.ai/news/"
    assert row["category"] == "ai-llm"
    assert row["kind"] == "scraped_page"
    assert row["priority"] == 80
    assert row["enabled"] is True


def test_mistral_ai_news_sync_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running sync_sources twice does not duplicate mistral-ai-news."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'mistral-ai-news'"
        ).fetchone()["c"]

    assert count == 1
