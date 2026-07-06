"""Tests for #1064 — merging duplicate-url articles during schema init.

Production already contains `articles` rows that share the same `url`
(pre-existing data corruption predating consistent `ON CONFLICT (url)` use on
every insert path). Because `url` is UNIQUE, a bulk UPDATE that rewrites those
rows (like the state backfill in POSTGRES_SCHEMA) surfaces the latent
duplicate as a UniqueViolation and crash-loops init_db(). These tests confirm
the dedupe migration step merges such rows instead of crashing, and repoints
per-user state onto the surviving "keeper" article.
"""

from __future__ import annotations

from news_dashboard import db as db_mod
from news_dashboard.auth import create_user
from news_dashboard.db import connect, init_db
from news_dashboard.ingest import sync_sources

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

    keeper_id = _insert_duplicate_article(db, title="First copy")
    loser_id = _insert_duplicate_article(db, title="Second copy")
    assert loser_id > keeper_id

    user = create_user("dupe-tester", "password123", db_path=db)
    with connect(db) as conn:
        # A state row on the keeper for this user, so repointing the loser's
        # row would collide with the (user_id, article_id) primary key.
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, state) VALUES (%s, %s, 'done')",
            (user["id"], keeper_id),
        )
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, state) VALUES (%s, %s, 'today')",
            (user["id"], loser_id),
        )

    other_user = create_user("dupe-tester-2", "password123", db_path=db)
    with connect(db) as conn:
        # Only the loser has state for this user, so it must be repointed
        # onto the keeper rather than dropped.
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, state) VALUES (%s, %s, 'later')",
            (other_user["id"], loser_id),
        )

    db_mod._INITIALIZED_DATABASES.clear()
    init_db(db)

    with connect(db) as conn:
        articles = conn.execute(
            "SELECT id FROM articles WHERE url = %s", (DUPLICATE_URL,)
        ).fetchall()
        assert len(articles) == 1
        assert int(articles[0]["id"]) == keeper_id

        state_rows = {
            row["user_id"]: (row["article_id"], row["state"])
            for row in conn.execute(
                "SELECT user_id, article_id, state FROM user_article_state WHERE article_id = %s",
                (keeper_id,),
            ).fetchall()
        }

    # The keeper's own state for the first user survives; the loser's
    # conflicting duplicate row for that user is dropped, not preferred.
    assert state_rows[user["id"]] == (keeper_id, "done")
    # The second user only had state on the loser, so it must be repointed.
    assert state_rows[other_user["id"]] == (keeper_id, "later")
