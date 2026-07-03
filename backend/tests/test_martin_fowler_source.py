"""Tests for Martin Fowler default source (issue #752)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest import sync_sources
from news_dashboard.sources import DEFAULT_SOURCES

# ── Unit tests (no DB) ───────────────────────────────────────────────────


def test_martin_fowler_in_default_sources() -> None:
    """martin-fowler SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "martin-fowler" in by_slug, f"martin-fowler not found; slugs: {sorted(by_slug)[:10]}..."


def test_martin_fowler_metadata() -> None:
    """martin-fowler has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "martin-fowler")
    assert src.name == "Martin Fowler"
    assert src.url == "https://martinfowler.com/feed.atom"
    assert src.category == "engineering"
    assert src.kind == "rss_feed"
    assert src.priority == 65
    assert src.enabled is True
    assert src.lang == "en"


def test_martin_fowler_interest_tags() -> None:
    """martin-fowler carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "martin-fowler")
    assert "infra" in src.interest_tags
    assert "software-development" in src.interest_tags
    assert "architecture" in src.interest_tags


def test_martin_fowler_routes_to_rss_feed() -> None:
    """martin-fowler kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "martin-fowler")
    assert src.kind == "rss_feed"


# ── Integration tests (PostgreSQL) ────────────────────────────────────────


def test_martin_fowler_sync_persists_row(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sync_sources() creates a sources row for martin-fowler."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'martin-fowler'"
        ).fetchone()

    assert row is not None, "martin-fowler row missing from sources table"
    assert row["slug"] == "martin-fowler"
    assert row["name"] == "Martin Fowler"
    assert row["url"] == "https://martinfowler.com/feed.atom"
    assert row["category"] == "engineering"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 65
    assert row["enabled"] is True


def test_martin_fowler_sync_idempotent(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running sync_sources twice does not duplicate martin-fowler."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'martin-fowler'"
        ).fetchone()["c"]

    assert count == 1
