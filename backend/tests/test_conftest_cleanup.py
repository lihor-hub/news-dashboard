"""Tests for the dynamic full-schema truncation used by the pg_clean fixture."""

from __future__ import annotations


def test_truncate_all_tables_clears_tables_missing_from_old_hardcoded_list(pg_url: str) -> None:
    """Every public table gets truncated, not just a hand-maintained subset.

    Regression test for a bug where pg_clean's old hardcoded TRUNCATE list
    silently drifted out of sync as new tables (user_goals, share_annotations,
    reading_list_items, ...) were added, leaking rows between tests.
    """
    import psycopg
    from conftest import truncate_all_tables

    from news_dashboard.db import connect, init_db

    init_db(database_url=pg_url)

    with connect(database_url=pg_url) as conn:
        conn.execute("INSERT INTO users(username, password_hash) VALUES ('cleanup-test', 'x')")
        user_row = conn.execute("SELECT id FROM users WHERE username = 'cleanup-test'").fetchone()
        user_id = int(user_row["id"])
        conn.execute(
            "INSERT INTO user_goals(user_id, description) VALUES (%s, 'Read more Rust news')",
            (user_id,),
        )

    truncate_all_tables(pg_url)

    with psycopg.connect(pg_url) as conn:
        goals_row = conn.execute("SELECT COUNT(*) FROM user_goals").fetchone()
        users_row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        assert goals_row is not None
        assert users_row is not None
        assert goals_row[0] == 0
        assert users_row[0] == 0


def test_truncate_all_tables_covers_every_table_the_schema_defines(pg_url: str) -> None:
    """No table is silently excluded from cleanup, and cleanup doesn't drop tables."""
    import psycopg
    from conftest import truncate_all_tables

    from news_dashboard.db import init_db

    init_db(database_url=pg_url)

    def _tables(conn: psycopg.Connection) -> set[str]:
        return {
            row[0]
            for row in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).fetchall()
        }

    with psycopg.connect(pg_url) as conn:
        before = _tables(conn)

    truncate_all_tables(pg_url)

    with psycopg.connect(pg_url) as conn:
        after = _tables(conn)

    assert before == after
    # Sanity: the schema has grown well past the old ~20-table hardcoded list.
    assert len(before) >= 25
