"""Tests for arXiv AI/ML default source (issue #750)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest.service import sync_sources
from news_dashboard.sources.service import DEFAULT_SOURCES

# ── Unit tests (no DB) ───────────────────────────────────────────────────


def test_arxiv_ai_ml_in_default_sources() -> None:
    """arxiv-ai-ml SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "arxiv-ai-ml" in by_slug, f"arxiv-ai-ml not found; slugs: {sorted(by_slug)[:10]}..."


def test_arxiv_ai_ml_metadata() -> None:
    """arxiv-ai-ml has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "arxiv-ai-ml")
    assert src.name == "arXiv AI/ML"
    assert src.url == "https://rss.arxiv.org/rss/cs.AI"
    assert src.category == "ai-research"
    assert src.kind == "rss_feed"
    assert src.priority == 70
    assert src.enabled is True
    assert src.lang == "en"


def test_arxiv_ai_ml_interest_tags() -> None:
    """arxiv-ai-ml carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "arxiv-ai-ml")
    assert "evals" in src.interest_tags
    assert "model-releases" in src.interest_tags
    assert "research" in src.interest_tags


def test_arxiv_ai_ml_routes_to_rss_feed() -> None:
    """arxiv-ai-ml kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "arxiv-ai-ml")
    assert src.kind == "rss_feed"


# ── Integration tests (PostgreSQL) ────────────────────────────────────────


def test_arxiv_ai_ml_sync_persists_row(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_sources() creates a sources row for arxiv-ai-ml."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'arxiv-ai-ml'"
        ).fetchone()

    assert row is not None, "arxiv-ai-ml row missing from sources table"
    assert row["slug"] == "arxiv-ai-ml"
    assert row["name"] == "arXiv AI/ML"
    assert row["url"] == "https://rss.arxiv.org/rss/cs.AI"
    assert row["category"] == "ai-research"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 70
    assert row["enabled"] is True


def test_arxiv_ai_ml_sync_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running sync_sources twice does not duplicate arxiv-ai-ml."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'arxiv-ai-ml'"
        ).fetchone()["c"]

    assert count == 1
