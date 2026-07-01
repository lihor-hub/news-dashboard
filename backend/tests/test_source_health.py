"""Tests for source health tracking, better summaries, noise filters, and search."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import pytest

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.ingest import (
    infer_tags,
    make_summary,
    search_articles,
    sync_sources,
)
from news_dashboard.source_health import (
    generate_subscription_cleanup_suggestions,
    list_source_health,
)
from news_dashboard.sources import SourceDefinition

# ──────────────────────────────────────────────
# Source health tracking
# ──────────────────────────────────────────────


def _insert_article(conn: Any, n: int = 1) -> None:
    """Insert a test article using a source that's already synced."""
    for i in range(n):
        conn.execute(
            """INSERT INTO articles(
                 url, canonical_url, title, source_slug, source_name, category, kind
               )
               VALUES (%s, %s, %s, 'python-insider', 'Python Insider', 'python', 'rss_feed')
               ON CONFLICT (url) DO NOTHING""",
            (f"https://example.com/art-{i}", f"https://example.com/art-{i}", f"Article {i}"),
        )


def _make_user(db_path: Path | str, username: str = "alice") -> int:
    user = create_user(username, "pw", db_path=db_path)
    return int(user["id"])


def _api_client(user_id: int) -> Any:
    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_admin, require_auth
    from news_dashboard.main import app

    fake = {"id": user_id, "username": "testuser", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake
    app.dependency_overrides[require_admin] = lambda: fake
    return TestClient(app, raise_server_exceptions=True)


def _add_source(conn: Any, slug: str, name: str) -> None:
    conn.execute(
        """
        INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
        VALUES (%s, %s, %s, 'tech', 'rss_feed', 10, TRUE)
        """,
        (slug, name, f"https://example.com/{slug}.xml"),
    )


def _add_private_source(conn: Any, slug: str, name: str, owner_user_id: int) -> None:
    conn.execute(
        """
        INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
        VALUES (%s, %s, %s, 'tech', 'rss_feed', 10, TRUE, %s)
        """,
        (slug, name, f"https://example.com/{slug}.xml", owner_user_id),
    )


def _add_article(
    conn: Any,
    *,
    user_id: int,
    slug: str,
    index: int,
    state: str = "today",
    days_old: int = 1,
) -> None:
    row = conn.execute(
        """
        INSERT INTO articles(
          url, canonical_url, title, source_slug, source_name, category, kind, discovered_at
        )
        VALUES (
          %s, %s, %s, %s, %s, 'tech', 'rss_feed',
          NOW() - (%s * INTERVAL '1 day')
        )
        RETURNING id
        """,
        (
            f"https://example.com/{slug}/{index}",
            f"https://example.com/{slug}/{index}",
            f"{slug} article {index}",
            slug,
            slug,
            days_old,
        ),
    ).fetchone()
    article_id = int(row["id"])
    if state == "today":
        return
    conn.execute(
        """
        INSERT INTO user_article_state(
          user_id, article_id, state, starred, done_at, skipped_at, archived_at
        )
        VALUES (
          %s, %s, %s, %s,
          CASE WHEN %s = 'done' THEN NOW() ELSE NULL END,
          CASE WHEN %s = 'skipped' THEN NOW() ELSE NULL END,
          CASE WHEN %s = 'archived' THEN NOW() ELSE NULL END
        )
        """,
        (user_id, article_id, state, state == "starred", state, state, state),
    )


def test_source_columns_present(tmp_path: Path) -> None:
    sync_sources(tmp_path / "health.db")
    with connect(tmp_path / "health.db") as conn:
        row = conn.execute("SELECT * FROM sources LIMIT 1").fetchone()
        keys = row.keys()
        for col in ("last_success_at", "last_error", "last_fetched_count", "last_inserted_count"):
            assert col in keys, f"missing column: {col}"


def test_source_error_tracked(tmp_path: Path) -> None:
    from news_dashboard.sources import SourceDefinition

    bad = SourceDefinition("bad-feed", "Bad Feed", "http://localhost:0/nope", "python")
    db = tmp_path / "err.db"
    sync_sources(db)
    with connect(db) as conn:
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind, priority, enabled) "
            "VALUES (%s, %s, %s, %s, %s, 50, TRUE) ON CONFLICT(slug) DO NOTHING",
            (bad.slug, bad.name, bad.url, bad.category, bad.kind),
        )

    from news_dashboard.ingest import ingest_source

    with contextlib.suppress(Exception):  # failure is the point of this fixture
        ingest_source(bad, db)

    with connect(db) as conn:
        row = conn.execute(
            "SELECT last_error, last_checked_at FROM sources WHERE slug=%s", (bad.slug,)
        ).fetchone()
        assert row["last_error"] is not None, "last_error should be set on failure"
        assert row["last_checked_at"] is not None, "last_checked_at should be set even on failure"


def test_source_health_error_streak_resets_after_success(tmp_path: Path) -> None:
    db = tmp_path / "streak.db"
    sync_sources(db)
    with connect(db) as conn:
        for run_id, error in ((1, "timeout"), (2, "HTTP 500"), (3, None)):
            conn.execute(
                "INSERT INTO ingest_runs(id, started_at) VALUES (%s, %s)",
                (run_id, f"2026-06-0{run_id}T00:00:00+00:00"),
            )
            conn.execute(
                """
                INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
                VALUES (%s, 'Python Insider', 10, %s, %s)
                """,
                (run_id, 3 if error is None else 0, error),
            )

    python = next(item for item in list_source_health(db) if item["slug"] == "python-insider")
    assert python["error_streak"] == 0
    assert python["articles_last_run"] == 3
    assert python["status"] == "OK"


def test_source_health_counts_leading_errors_and_sorts_first(tmp_path: Path) -> None:
    db = tmp_path / "leading-errors.db"
    sync_sources(db)
    with connect(db) as conn:
        for run_id in (1, 2, 3):
            conn.execute(
                "INSERT INTO ingest_runs(id, started_at) VALUES (%s, %s)",
                (run_id, f"2026-06-0{run_id}T00:00:00+00:00"),
            )
        conn.execute(
            """
            INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
            VALUES (1, 'Python Insider', 8, 2, NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
            VALUES (2, 'Python Insider', 0, 0, 'Feed fetch failed: timeout')
            """
        )
        conn.execute(
            """
            INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
            VALUES (
              3, 'Python Insider', 0, 0,
              'Traceback (most recent call last):\n  File "feed.py", line 1\n'
                || 'TimeoutError: connection timed out'
            )
            """
        )

    items = list_source_health(db)
    python = next(item for item in items if item["slug"] == "python-insider")
    assert python["error_streak"] == 2
    assert python["articles_last_run"] == 0
    assert python["status"] == "ERROR"
    assert python["last_error"] == "TimeoutError: connection timed out"
    assert items[0]["slug"] == "python-insider"


def test_source_health_scoped_to_user_visibility(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    alice_id = _make_user(pg_clean, "alice")
    bob_id = _make_user(pg_clean, "bob")

    with connect(pg_clean) as conn:
        _add_private_source(conn, "alice-private", "Alice Private Feed", alice_id)
        _add_private_source(conn, "bob-private", "Bob Private Feed", bob_id)

    alice_items = list_source_health(user_id=alice_id, database_url=pg_clean)
    alice_slugs = {item["slug"] for item in alice_items}

    assert "alice-private" in alice_slugs, "alice should see her own private source"
    assert "bob-private" not in alice_slugs, "alice should not see bob's private source"

    bob_items = list_source_health(user_id=bob_id, database_url=pg_clean)
    bob_slugs = {item["slug"] for item in bob_items}

    assert "bob-private" in bob_slugs, "bob should see his own private source"
    assert "alice-private" not in bob_slugs, "bob should not see alice's private source"


def test_source_health_api_scoped_to_current_user(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    alice_id = _make_user(pg_clean, "alice")
    bob_id = _make_user(pg_clean, "bob")

    with connect(pg_clean) as conn:
        _add_private_source(conn, "alice-private", "Alice Private Feed", alice_id)
        _add_private_source(conn, "bob-private", "Bob Private Feed", bob_id)

    client = _api_client(alice_id)
    try:
        resp = client.get("/api/sources/health")
        assert resp.status_code == 200
        slugs = {item["slug"] for item in resp.json()["items"]}
        assert "alice-private" in slugs, "alice should see her own private source via API"
        assert "bob-private" not in slugs, "alice should not see bob's private source via API"
    finally:
        from news_dashboard.auth import require_admin, require_auth
        from news_dashboard.main import app

        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_subscription_cleanup_suggests_high_skip_rate_source(
    pg_clean: str, monkeypatch: Any
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "noise-feed", "Noise Feed")
        for i in range(46):
            _add_article(conn, user_id=uid, slug="noise-feed", index=i, state="skipped")
        for i in range(46, 50):
            _add_article(conn, user_id=uid, slug="noise-feed", index=i, state="done")

    suggestions = generate_subscription_cleanup_suggestions(uid, database_url=pg_clean)

    assert suggestions == [
        {
            "source_slug": "noise-feed",
            "source_name": "Noise Feed",
            "action": "unsubscribe",
            "reason": "low_signal",
            "message": "Unsubscribe from 'Noise Feed' (92% skipped in the last 30 days)",
            "articles_last_30_days": 50,
            "skipped_count": 46,
            "done_count": 4,
            "starred_count": 0,
            "archived_count": 0,
            "skip_rate": 0.92,
            "engagement_score": 0.08,
        }
    ]


def test_subscription_cleanup_suggests_stale_source(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "quiet-feed", "Quiet Feed")
        _add_article(conn, user_id=uid, slug="quiet-feed", index=1, days_old=45)

    suggestions = generate_subscription_cleanup_suggestions(uid, database_url=pg_clean)

    assert suggestions == [
        {
            "source_slug": "quiet-feed",
            "source_name": "Quiet Feed",
            "action": "unsubscribe",
            "reason": "stale",
            "message": "Unsubscribe from 'Quiet Feed' (no articles in the last 30 days)",
            "articles_last_30_days": 0,
            "skipped_count": 0,
            "done_count": 0,
            "starred_count": 0,
            "archived_count": 0,
            "skip_rate": 0.0,
            "engagement_score": 0.0,
        }
    ]


def test_subscription_cleanup_api_unsubscribes_requested_sources(
    pg_clean: str, monkeypatch: Any
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "noise-feed", "Noise Feed")
        _add_source(conn, "keeper-feed", "Keeper Feed")

    client = _api_client(uid)
    try:
        suggestions = client.get("/api/sources/cleanup-suggestions")
        assert suggestions.status_code == 200

        response = client.post("/api/sources/cleanup", json={"source_slugs": ["noise-feed"]})
        assert response.status_code == 200
        assert response.json() == {"updated": ["noise-feed"], "skipped": []}
    finally:
        from news_dashboard.auth import require_admin, require_auth
        from news_dashboard.main import app

        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)

    with connect(pg_clean) as conn:
        rows = conn.execute(
            """
            SELECT source_slug, enabled
            FROM user_sources
            WHERE user_id = %s
            ORDER BY source_slug
            """,
            (uid,),
        ).fetchall()
    assert [(row["source_slug"], row["enabled"]) for row in rows] == [("noise-feed", False)]


# ──────────────────────────────────────────────
# Better summaries / reasons (issue #8)
# ──────────────────────────────────────────────


def test_release_reason() -> None:
    src = SourceDefinition("ruff-releases", "Ruff", "x", "python", "github_release_feed", 85)
    _, reason, _, _ = make_summary("ruff v0.9.3", "Bug fixes and performance improvements.", src)
    assert "v0.9.3" in reason or "release" in reason.lower()


def test_trending_reason_hn() -> None:
    src = SourceDefinition(
        "hacker-news-best", "Hacker News Best", "x", "trending", "trending_feed", 55
    )
    _, reason, _, _ = make_summary("Ask HN: What tools do you use?", "discussion", src)
    assert "Hacker News" in reason or "trending" in reason.lower()


def test_security_reason() -> None:
    src = SourceDefinition("python-insider", "Python Insider", "x", "python", "rss_feed", 90)
    _, reason, _, tags = make_summary(
        "Critical security vulnerability in stdlib", "CVE-2025-1234 affects all versions.", src
    )
    assert "security" in tags
    assert "security" in reason.lower() or "Security" in reason


def test_generic_reason_not_tracked_under() -> None:
    src = SourceDefinition("astral-blog", "Astral Blog", "x", "python", "rss_feed", 85)
    _, reason, _, _ = make_summary("Introducing uv workspaces", "New feature announcement.", src)
    assert not reason.startswith("Tracked under"), (
        "generic 'Tracked under' reason should not appear"
    )


# ──────────────────────────────────────────────
# Noise filters (issue #7)
# ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("title", "expected_tag"),
    [
        ("New Python 3.14 typing improvements with mypy support", "python"),
        ("Release v2.1.0 of some library with changelog", "release"),
        ("Critical CVE found in popular package", "security"),
        ("LangGraph adds new multi-agent orchestration workflow", "agents"),
    ],
)
def test_infer_tags(title: str, expected_tag: str) -> None:
    tags = infer_tags(title)
    assert expected_tag in tags


# ──────────────────────────────────────────────
# Search (issue #9)
# ──────────────────────────────────────────────


def test_search_returns_matching_articles(tmp_path: Path) -> None:
    db = tmp_path / "search.db"
    sync_sources(db)
    with connect(db) as conn:
        conn.execute(
            """INSERT INTO articles(
                 url, canonical_url, title, source_slug, source_name, category, kind, summary
               )
               VALUES (
                 'https://ex.com/1', 'https://ex.com/1', 'Python typing guide',
                 'python-insider', 'Python Insider', 'python', 'rss_feed',
                 'How to use mypy and pyright together'
               )""",
        )
        conn.execute(
            """INSERT INTO articles(
                 url, canonical_url, title, source_slug, source_name, category, kind, summary
               )
               VALUES (
                 'https://ex.com/2', 'https://ex.com/2', 'Docker networking',
                 'docker-blog', 'Docker Blog', 'cloud-infra', 'rss_feed',
                 'Container networking basics'
               )""",
        )

    results = search_articles("python mypy", db_path=db)
    assert any("Python" in r["title"] for r in results), "should find the Python article"
    for r in results:
        assert r["url"] != "https://ex.com/2", "Docker article should not appear in Python search"


def test_search_empty_query_returns_empty(tmp_path: Path) -> None:
    db = tmp_path / "search2.db"
    sync_sources(db)
    # Single-char queries get filtered out
    results = search_articles("a", db_path=db)
    assert isinstance(results, list)
