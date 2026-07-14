"""Regression tests for source-visibility-aware article deduplication.

Covers:
- Global-source-first / private-source-second: private duplicate must NOT
  displace the global canonical for other users.
- Private-source-first / global-source-second: global article must NOT be
  hidden behind a private canonical.
- Same-owner private duplicate deduplicates against the private canonical.
- Two-owner private articles do NOT deduplicate against each other.
- _attach_also_from is user-scoped: private source names are excluded from
  other users' also_from lists.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import news_dashboard.ingest.service as ingest_module
from news_dashboard.db import connect
from news_dashboard.sources.service import SourceDefinition

_attach_also_from = ingest_module._attach_also_from
_find_canonical = ingest_module._find_canonical
canonicalize_url = ingest_module.canonicalize_url

# ── helpers ───────────────────────────────────────────────────────────────────


def _insert_user(pg_url: str, username: str) -> int:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'x') RETURNING id",
            (username,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_source(pg_url: str, slug: str, owner_user_id: int | None = None) -> None:
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, owner_user_id)
            VALUES (%s, %s, 'https://example.com', 'tech', 'rss_feed', %s)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug, owner_user_id),
        )


def _insert_canonical(pg_url: str, url: str, title: str, source_slug: str) -> int:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug, source_name,
                                 category, kind)
            VALUES (%s, %s, %s, %s, %s, 'tech', 'rss_feed')
            RETURNING id
            """,
            (url, url, title, source_slug, source_slug),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_duplicate(
    pg_url: str, url: str, title: str, source_slug: str, canonical_id: int
) -> int:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug, source_name,
                                 category, kind, canonical_id, state)
            VALUES (%s, %s, %s, %s, %s, 'tech', 'rss_feed', %s, 'archived')
            RETURNING id
            """,
            (url, url, title, source_slug, source_slug, canonical_id),
        ).fetchone()
    assert row is not None
    return int(row["id"])


# ── _find_canonical tests ─────────────────────────────────────────────────────


def test_global_first_private_second_does_not_hide_global(pg_clean: str) -> None:
    """A global article inserted first should be the canonical.
    A later private source must find the global canonical but that
    canonical remains global — other users can still see it."""
    _insert_source(pg_clean, "global-src")
    global_id = _insert_canonical(pg_clean, "https://a.com/story", "Big Story Today", "global-src")

    uid = _insert_user(pg_clean, "alice")
    _insert_source(pg_clean, "alice-private", owner_user_id=uid)

    with connect(database_url=pg_clean) as conn:
        # Alice's private source should find the global canonical
        found = _find_canonical(conn, "https://a.com/story", "Big Story Today", owner_user_id=uid)

    assert found == global_id


def test_private_first_global_second_finds_no_private_canonical(pg_clean: str) -> None:
    """A private article inserted first must NOT become the canonical for a global source.
    The global source can only canonicalize against other global articles."""
    uid = _insert_user(pg_clean, "bob")
    _insert_source(pg_clean, "bob-private", owner_user_id=uid)
    _insert_canonical(pg_clean, "https://b.com/story", "Breaking News Now", "bob-private")

    _insert_source(pg_clean, "global-src")

    with connect(database_url=pg_clean) as conn:
        # Global source must NOT canonicalize against the private article
        found = _find_canonical(
            conn, "https://b.com/story", "Breaking News Now", owner_user_id=None
        )

    assert found is None


def test_global_dedupes_against_global(pg_clean: str) -> None:
    """Two global sources with the same URL should deduplicate."""
    _insert_source(pg_clean, "global-src-1")
    global_id = _insert_canonical(
        pg_clean, "https://c.com/story", "Tech Event 2026", "global-src-1"
    )

    _insert_source(pg_clean, "global-src-2")

    with connect(database_url=pg_clean) as conn:
        found = _find_canonical(conn, "https://c.com/story", "Tech Event 2026", owner_user_id=None)

    assert found == global_id


def test_same_owner_private_deduplicates(pg_clean: str) -> None:
    """A user's second private source should deduplicate against the same owner's first."""
    uid = _insert_user(pg_clean, "carol")
    _insert_source(pg_clean, "carol-private-1", owner_user_id=uid)
    private_id = _insert_canonical(
        pg_clean, "https://d.com/story", "Private Scoop", "carol-private-1"
    )

    _insert_source(pg_clean, "carol-private-2", owner_user_id=uid)

    with connect(database_url=pg_clean) as conn:
        found = _find_canonical(conn, "https://d.com/story", "Private Scoop", owner_user_id=uid)

    assert found == private_id


def test_different_owner_private_does_not_deduplicate(pg_clean: str) -> None:
    """Private articles from different users must NOT deduplicate against each other."""
    uid1 = _insert_user(pg_clean, "dave")
    _insert_source(pg_clean, "dave-private", owner_user_id=uid1)
    _insert_canonical(pg_clean, "https://e.com/story", "Exclusive Report", "dave-private")

    uid2 = _insert_user(pg_clean, "eve")
    _insert_source(pg_clean, "eve-private", owner_user_id=uid2)

    with connect(database_url=pg_clean) as conn:
        # Eve's source must NOT match Dave's private canonical
        found = _find_canonical(conn, "https://e.com/story", "Exclusive Report", owner_user_id=uid2)

    assert found is None


# ── _attach_also_from user-scoping tests ──────────────────────────────────────


def test_also_from_excludes_other_users_private_source(pg_clean: str) -> None:
    """A private duplicate from user A must not appear in also_from for user B."""
    _insert_source(pg_clean, "global-src")
    canonical_id = _insert_canonical(pg_clean, "https://f.com/story", "Shared Story", "global-src")

    uid_a = _insert_user(pg_clean, "frank")
    _insert_source(pg_clean, "frank-private", owner_user_id=uid_a)
    _insert_duplicate(
        pg_clean, "https://f.com/story-private", "Shared Story", "frank-private", canonical_id
    )

    uid_b = _insert_user(pg_clean, "grace")

    article: dict[str, Any] = {"id": canonical_id}
    with connect(database_url=pg_clean) as conn:
        _attach_also_from(conn, [article], user_id=uid_b)

    # Grace cannot see Frank's private source
    assert "frank-private" not in article["also_from"]


def test_also_from_includes_own_private_source(pg_clean: str) -> None:
    """A user's own private duplicate must appear in their own also_from."""
    _insert_source(pg_clean, "global-src")
    canonical_id = _insert_canonical(pg_clean, "https://g.com/story", "My Story", "global-src")

    uid = _insert_user(pg_clean, "hank")
    _insert_source(pg_clean, "hank-private", owner_user_id=uid)
    _insert_duplicate(pg_clean, "https://g.com/story-dup", "My Story", "hank-private", canonical_id)

    article: dict[str, Any] = {"id": canonical_id}
    with connect(database_url=pg_clean) as conn:
        _attach_also_from(conn, [article], user_id=uid)

    assert "hank-private" in article["also_from"]


def test_also_from_includes_global_duplicate_for_all_users(pg_clean: str) -> None:
    """Global source duplicates are visible to all users in also_from."""
    _insert_source(pg_clean, "global-src-1")
    canonical_id = _insert_canonical(pg_clean, "https://h.com/story", "World News", "global-src-1")

    _insert_source(pg_clean, "global-src-2")
    _insert_duplicate(pg_clean, "https://h.com/story2", "World News", "global-src-2", canonical_id)

    uid = _insert_user(pg_clean, "ivan")

    article: dict[str, Any] = {"id": canonical_id}
    with connect(database_url=pg_clean) as conn:
        _attach_also_from(conn, [article], user_id=uid)

    assert "global-src-2" in article["also_from"]


def test_also_from_no_user_includes_all_sources(pg_clean: str) -> None:
    """The legacy (no user_id) path includes all duplicate sources for admin use."""
    _insert_source(pg_clean, "global-src")
    canonical_id = _insert_canonical(pg_clean, "https://i.com/story", "Admin View", "global-src")

    uid = _insert_user(pg_clean, "judy")
    _insert_source(pg_clean, "judy-private", owner_user_id=uid)
    _insert_duplicate(
        pg_clean, "https://i.com/story-dup", "Admin View", "judy-private", canonical_id
    )

    article: dict[str, Any] = {"id": canonical_id}
    with connect(database_url=pg_clean) as conn:
        _attach_also_from(conn, [article])

    # Admin path sees private source name too
    assert "judy-private" in article["also_from"]


# ── URL-variant reappearance regression (issue #1215) ─────────────────────────


def _age_article(pg_url: str, article_id: int, days: int) -> None:
    """Push discovered_at into the past so the 7-day fuzzy-title fallback in
    _find_canonical can no longer rescue a URL-match miss — isolating the
    URL-normalization path from the title-fallback path."""
    with connect(database_url=pg_url) as conn:
        conn.execute(
            "UPDATE articles SET discovered_at = %s WHERE id = %s",
            ((datetime.now(timezone.utc) - timedelta(days=days)).isoformat(), article_id),
        )


def test_find_canonical_matches_scheme_and_trailing_slash_variant(pg_clean: str) -> None:
    """A URL that differs only by scheme/case/trailing-slash must still match
    the existing canonical once both sides are canonicalized — otherwise a
    re-ingested article gets a brand-new id with no user_article_state row,
    making it reappear in the Today feed after the user already triaged it.

    The canonical is aged past the 7-day fuzzy-title fallback window so this
    test exercises URL matching specifically, not the title fallback."""
    _insert_source(pg_clean, "global-src")
    canonical_url = canonicalize_url("https://Example.test/story/")
    canonical_id = _insert_canonical(pg_clean, canonical_url, "Big Story", "global-src")
    _age_article(pg_clean, canonical_id, days=10)

    variant_url = canonicalize_url("HTTPS://example.TEST/story")

    with connect(database_url=pg_clean) as conn:
        found = _find_canonical(conn, variant_url, "Big Story", owner_user_id=None)

    assert found == canonical_id


def test_ingest_all_does_not_duplicate_url_variant_across_runs(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Two ingest runs serving the same article as a scheme/trailing-slash/
    tracking-param variant must not create two distinct (non-archived)
    articles rows — a second row would have no user_article_state and would
    reappear in the Today feed even after the first was triaged.

    The first run's article is aged past the fuzzy-title fallback window so
    this test exercises URL matching specifically, not the title fallback."""

    db_path = tmp_path / "reingest.db"
    source = SourceDefinition("test-feed", "Test Feed", "https://example.com/feed.xml", "python")
    monkeypatch.setattr(ingest_module, "DEFAULT_SOURCES", [source])

    urls = iter(
        [
            "https://example.com/article/",
            "HTTPS://Example.com/article?utm_source=rss",
        ]
    )

    def fake_parse_url(url: str) -> list[dict[str, object]]:
        return [
            {
                "url": next(urls),
                "title": "Same Story Twice",
                "description": "A summary.",
                "date": None,
            }
        ]

    monkeypatch.setattr(ingest_module, "_parse_feed_url", fake_parse_url)

    ingest_module.ingest_all(db_path)
    with connect(db_path) as conn:
        first = conn.execute("SELECT id FROM articles WHERE canonical_id IS NULL").fetchone()
        assert first is not None
        conn.execute(
            "UPDATE articles SET discovered_at = %s WHERE id = %s",
            (
                (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                first["id"] if isinstance(first, dict) else first[0],
            ),
        )

    ingest_module.ingest_all(db_path)

    with connect(db_path) as conn:
        rows = conn.execute("SELECT id FROM articles WHERE canonical_id IS NULL").fetchall()

    assert len(rows) == 1
