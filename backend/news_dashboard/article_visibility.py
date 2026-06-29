"""Article source-visibility helpers.

Runtime SQL is PostgreSQL-specific and uses psycopg ``%s`` parameters.
"""

from __future__ import annotations

from typing import Any


def visible_article_sql(alias: str = "a") -> str:
    """Return the source-visibility predicate for an article table alias."""
    return (
        f"({alias}_src.owner_user_id IS NULL AND COALESCE({alias}_us.enabled, TRUE)) "
        f"OR {alias}_src.owner_user_id = %s"
    )


def get_visible_article_row(conn: Any, article_id: int, user_id: int | None) -> Any | None:
    """Return an article row only when it is visible to ``user_id``.

    Userless callers keep the legacy article-id-only behavior for CLI/background
    paths. User-scoped callers see global subscribed sources plus their own
    private sources.
    """
    if user_id is None:
        return conn.execute("SELECT * FROM articles WHERE id = %s", (article_id,)).fetchone()

    return conn.execute(
        f"""
        SELECT a.*
        FROM articles a
        JOIN sources a_src ON a_src.slug = a.source_slug
        LEFT JOIN user_sources a_us
          ON a_us.source_slug = a.source_slug AND a_us.user_id = %s
        WHERE a.id = %s
          AND ({visible_article_sql("a")})
        """,
        (user_id, article_id, user_id),
    ).fetchone()
