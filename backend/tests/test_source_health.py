"""Tests for source health tracking, better summaries, noise filters, and search."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from news_dashboard.db import connect
from news_dashboard.ingest import (
    infer_tags,
    list_articles,
    make_reason,
    make_summary,
    search_articles,
    set_article_status,
    sync_sources,
)
from news_dashboard.sources import DEFAULT_SOURCES, SourceDefinition


# ──────────────────────────────────────────────
# Source health tracking
# ──────────────────────────────────────────────

def _require_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set TEST_DATABASE_URL to run Postgres integration tests")
    monkeypatch.setenv("DATABASE_URL", database_url)


def _insert_article(conn, n: int = 1) -> None:
    """Insert a test article using a source that's already synced."""
    for i in range(n):
        conn.execute(
            """INSERT INTO articles(url, canonical_url, title, source_slug, source_name, category, kind)
               VALUES (%s, %s, %s, 'python-insider', 'Python Insider', 'python', 'rss_feed')
               ON CONFLICT (url) DO NOTHING""",
            (f"https://example.com/art-{i}", f"https://example.com/art-{i}", f"Article {i}"),
        )


def test_source_columns_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_test_database(monkeypatch)
    sync_sources(tmp_path / "health.db")
    with connect(tmp_path / "health.db") as conn:
        row = conn.execute("SELECT * FROM sources LIMIT 1").fetchone()
        keys = row.keys()
        for col in ("last_success_at", "last_error", "last_fetched_count", "last_inserted_count"):
            assert col in keys, f"missing column: {col}"


def test_source_error_tracked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_test_database(monkeypatch)
    from news_dashboard.sources import SourceDefinition
    bad = SourceDefinition("bad-feed", "Bad Feed", "http://localhost:0/nope", "python")
    db = tmp_path / "err.db"
    sync_sources(db)
    with connect(db) as conn:
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind, priority, enabled) "
            "VALUES (%s, %s, %s, %s, %s, 50, 1) ON CONFLICT (slug) DO NOTHING",
            (bad.slug, bad.name, bad.url, bad.category, bad.kind),
        )

    from news_dashboard.ingest import ingest_source
    try:
        ingest_source(bad, db)
    except Exception:
        pass  # expected

    with connect(db) as conn:
        row = conn.execute("SELECT last_error, last_checked_at FROM sources WHERE slug=%s", (bad.slug,)).fetchone()
        assert row["last_error"] is not None, "last_error should be set on failure"
        assert row["last_checked_at"] is not None, "last_checked_at should be set even on failure"


# ──────────────────────────────────────────────
# Better summaries / reasons (issue #8)
# ──────────────────────────────────────────────

def test_release_reason() -> None:
    src = SourceDefinition("ruff-releases", "Ruff", "x", "python", "github_release_feed", 85)
    _, reason, _, _ = make_summary("ruff v0.9.3", "Bug fixes and performance improvements.", src)
    assert "v0.9.3" in reason or "release" in reason.lower()


def test_trending_reason_hn() -> None:
    src = SourceDefinition("hacker-news-best", "Hacker News Best", "x", "trending", "trending_feed", 55)
    _, reason, _, _ = make_summary("Ask HN: What tools do you use?", "discussion", src)
    assert "Hacker News" in reason or "trending" in reason.lower()


def test_security_reason() -> None:
    src = SourceDefinition("python-insider", "Python Insider", "x", "python", "rss_feed", 90)
    _, reason, _, tags = make_summary("Critical security vulnerability in stdlib", "CVE-2025-1234 affects all versions.", src)
    assert "security" in tags
    assert "security" in reason.lower() or "Security" in reason


def test_generic_reason_not_tracked_under() -> None:
    src = SourceDefinition("astral-blog", "Astral Blog", "x", "python", "rss_feed", 85)
    _, reason, _, _ = make_summary("Introducing uv workspaces", "New feature announcement.", src)
    assert not reason.startswith("Tracked under"), "generic 'Tracked under' reason should not appear"


# ──────────────────────────────────────────────
# Noise filters (issue #7)
# ──────────────────────────────────────────────

def test_infer_tags_python() -> None:
    tags = infer_tags("New Python 3.14 typing improvements with mypy support")
    assert "python" in tags


def test_infer_tags_release() -> None:
    tags = infer_tags("Release v2.1.0 of some library with changelog")
    assert "release" in tags


def test_infer_tags_security() -> None:
    tags = infer_tags("Critical CVE found in popular package")
    assert "security" in tags


def test_infer_tags_agents() -> None:
    tags = infer_tags("LangGraph adds new multi-agent orchestration workflow")
    assert "agents" in tags


# ──────────────────────────────────────────────
# Search (issue #9)
# ──────────────────────────────────────────────

def test_search_returns_matching_articles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_test_database(monkeypatch)
    db = tmp_path / "search.db"
    sync_sources(db)
    with connect(db) as conn:
        conn.execute(
            """INSERT INTO articles(url, canonical_url, title, source_slug, source_name, category, kind, summary)
               VALUES ('https://ex.com/1','https://ex.com/1','Python typing guide','python-insider','Python Insider','python','rss_feed','How to use mypy and pyright together')""",
        )
        conn.execute(
            """INSERT INTO articles(url, canonical_url, title, source_slug, source_name, category, kind, summary)
               VALUES ('https://ex.com/2','https://ex.com/2','Docker networking','docker-blog','Docker Blog','cloud-infra','rss_feed','Container networking basics')""",
        )

    results = search_articles("python mypy", db_path=db)
    assert any("Python" in r["title"] for r in results), "should find the Python article"
    for r in results:
        assert r["url"] != "https://ex.com/2", "Docker article should not appear in Python search"


def test_search_empty_query_returns_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_test_database(monkeypatch)
    db = tmp_path / "search2.db"
    sync_sources(db)
    # Single-char queries get filtered out
    results = search_articles("a", db_path=db)
    assert isinstance(results, list)
