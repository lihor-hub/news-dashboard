"""Tests for Google Project Zero default source (issue #767)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest.service import sync_sources
from news_dashboard.sources.service import DEFAULT_SOURCES

# Unit tests (no DB)


def test_google_project_zero_in_default_sources() -> None:
    """google-project-zero SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "google-project-zero" in by_slug, (
        f"google-project-zero not found; slugs: {sorted(by_slug)[:10]}..."
    )


def test_google_project_zero_metadata() -> None:
    """google-project-zero has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "google-project-zero")
    assert src.name == "Google Project Zero"
    assert (
        src.url
        == "https://googleprojectzero.blogspot.com/feeds/posts/summary?alt=rss&max-results=25"
    )
    assert src.category == "security"
    assert src.kind == "rss_feed"
    assert src.priority == 82
    assert src.enabled is True
    assert src.lang == "en"


def test_google_project_zero_interest_tags() -> None:
    """google-project-zero carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "google-project-zero")
    assert "security" in src.interest_tags
    assert "research" in src.interest_tags


def test_google_project_zero_routes_to_rss_feed() -> None:
    """google-project-zero kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "google-project-zero")
    assert src.kind == "rss_feed"


# Integration tests (PostgreSQL)


def test_google_project_zero_sync_persists_row(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_sources() creates a sources row for google-project-zero."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'google-project-zero'"
        ).fetchone()

    assert row is not None, "google-project-zero row missing from sources table"
    assert row["slug"] == "google-project-zero"
    assert row["name"] == "Google Project Zero"
    assert (
        row["url"]
        == "https://googleprojectzero.blogspot.com/feeds/posts/summary?alt=rss&max-results=25"
    )
    assert row["category"] == "security"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 82
    assert row["enabled"] is True


def test_google_project_zero_sync_idempotent(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running sync_sources twice does not duplicate google-project-zero."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'google-project-zero'"
        ).fetchone()["c"]

    assert count == 1
