"""Tests for #1064 — merging duplicate-url articles during schema init.

Production already contains `articles` rows that share the same `url`
(pre-existing data corruption predating consistent `ON CONFLICT (url)` use on
every insert path). Because `url` is UNIQUE, a bulk UPDATE that rewrites those
rows (like the state backfill in POSTGRES_SCHEMA) surfaces the latent
duplicate as a UniqueViolation and crash-loops init_db(). These tests confirm
the dedupe migration step archives the duplicate onto the surviving "keeper"
article, in place, instead of crashing or deleting per-user state.
"""

from __future__ import annotations

from news_dashboard import db as db_mod
from news_dashboard.auth import create_user
from news_dashboard.db import connect, init_db
from news_dashboard.ingest.service import sync_sources

DUPLICATE_URL = "https://example.com/duplicate-article"


def _drop_url_unique_constraint(db_path: str) -> None:
    """Simulate the pre-existing production corruption behind #1064.

    `articles_url_key` has always been declared on the table, so a live app
    can never insert a real duplicate; the constraint must be dropped to
    reproduce rows that already violate it, matching what's actually in
    production today.
    """
    with connect(db_path) as conn:
        conn.execute("ALTER TABLE articles DROP CONSTRAINT articles_url_key")


def _insert_duplicate_article(db_path: str, *, title: str) -> int:
    """Insert an articles row directly, bypassing the app's ON CONFLICT guard."""
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug, source_name,
              category, kind)
            VALUES (%s, %s, %s, %s, %s, 'tech', 'rss_feed')
            RETURNING id
            """,
            (DUPLICATE_URL, DUPLICATE_URL, title, "python-insider", "Python Insider"),
        ).fetchone()
    return int(row[0] if isinstance(row, tuple) else row["id"])


def test_init_db_merges_duplicate_url_articles(pg_clean: str) -> None:
    db = pg_clean
    sync_sources(db)
    _drop_url_unique_constraint(db)
    # pg_clean's schema is reused by later tests in this worker; leaving the
    # constraint dropped would break their ON CONFLICT (url) inserts.
    try:
        _run_merge_test(db)
    finally:
        with connect(db) as conn:
            conn.execute("ALTER TABLE articles ADD CONSTRAINT articles_url_key UNIQUE (url)")


def _run_merge_test(db: str) -> None:
    keeper_id = _insert_duplicate_article(db, title="First copy")
    loser_id = _insert_duplicate_article(db, title="Second copy")
    assert loser_id > keeper_id

    user = create_user("dupe-tester", "password123", db_path=db)
    with connect(db) as conn:
        # Each duplicate has its own per-user state, referencing its own
        # article id. Nothing here is repointed, so no PK collision is
        # possible even when the same user triaged both duplicates.
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, state) VALUES (%s, %s, 'done')",
            (user["id"], keeper_id),
        )
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, state) VALUES (%s, %s, 'today')",
            (user["id"], loser_id),
        )

    db_mod._INITIALIZED_DATABASES.clear()
    init_db(db)

    with connect(db) as conn:
        keeper = conn.execute(
            "SELECT url, state, status, canonical_id FROM articles WHERE id = %s",
            (keeper_id,),
        ).fetchone()
        loser = conn.execute(
            "SELECT url, state, status, canonical_id FROM articles WHERE id = %s",
            (loser_id,),
        ).fetchone()

        state_rows = {
            row["article_id"]: row["state"]
            for row in conn.execute(
                "SELECT article_id, state FROM user_article_state WHERE user_id = %s",
                (user["id"],),
            ).fetchall()
        }

    # The keeper keeps the real url and is never archived by the merge.
    assert keeper["url"] == DUPLICATE_URL
    assert keeper["canonical_id"] is None

    # The loser is archived in place and points at the keeper, rather than
    # being deleted — its url is freed up so it no longer collides.
    assert loser["url"] != DUPLICATE_URL
    assert loser["state"] == "archived"
    assert loser["status"] == "archived"
    assert int(loser["canonical_id"]) == keeper_id

    # Both duplicates' own per-user state survive untouched, on their own ids.
    assert state_rows[keeper_id] == "done"
    assert state_rows[loser_id] == "today"
