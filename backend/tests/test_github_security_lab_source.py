"""Tests for GitHub Security Lab default source (issue #769)."""

from __future__ import annotations

import pytest

from news_dashboard.ingest import sync_sources
from news_dashboard.sources import DEFAULT_SOURCES

# Unit tests (no DB)


def test_github_security_lab_in_default_sources() -> None:
    """github-security-lab SourceDefinition exists in DEFAULT_SOURCES."""
    by_slug = {s.slug: s for s in DEFAULT_SOURCES}
    assert "github-security-lab" in by_slug, (
        f"github-security-lab not found; slugs: {sorted(by_slug)[:10]}..."
    )


def test_github_security_lab_metadata() -> None:
    """github-security-lab has the expected metadata fields."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "github-security-lab")
    assert src.name == "GitHub Security Lab"
    assert src.url == "https://github.blog/tag/github-security-lab/feed/"
    assert src.category == "security"
    assert src.kind == "rss_feed"
    assert src.priority == 74
    assert src.enabled is True
    assert src.lang == "en"


def test_github_security_lab_interest_tags() -> None:
    """github-security-lab carries tags that match onboarding interests."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "github-security-lab")
    assert "security" in src.interest_tags
    assert "infra" in src.interest_tags
    assert "product-news" in src.interest_tags


def test_github_security_lab_routes_to_rss_feed() -> None:
    """github-security-lab kind is rss_feed, which ingest routes correctly."""
    src = next(s for s in DEFAULT_SOURCES if s.slug == "github-security-lab")
    assert src.kind == "rss_feed"


# Integration tests (PostgreSQL)


def test_github_security_lab_sync_persists_row(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_sources() creates a sources row for github-security-lab."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT slug, name, url, category, kind, priority, enabled "
            "FROM sources WHERE slug = 'github-security-lab'"
        ).fetchone()

    assert row is not None, "github-security-lab row missing from sources table"
    assert row["slug"] == "github-security-lab"
    assert row["name"] == "GitHub Security Lab"
    assert row["url"] == "https://github.blog/tag/github-security-lab/feed/"
    assert row["category"] == "security"
    assert row["kind"] == "rss_feed"
    assert row["priority"] == 74
    assert row["enabled"] is True


def test_github_security_lab_sync_idempotent(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running sync_sources twice does not duplicate github-security-lab."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    sync_sources(pg_clean)

    from news_dashboard.db import connect

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sources WHERE slug = 'github-security-lab'"
        ).fetchone()["c"]

    assert count == 1
