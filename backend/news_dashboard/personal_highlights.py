"""Private per-user article highlights.

Runtime SQL is PostgreSQL-specific and uses psycopg ``%s`` parameters.
"""

from __future__ import annotations

from typing import Any

from news_dashboard.article_visibility import get_visible_article_row
from news_dashboard.db import connect, row_to_dict


def list_highlights(article_id: int, user_id: int) -> list[dict[str, Any]] | None:
    """Return a user's highlights for a visible article, oldest first."""
    with connect() as conn:
        if get_visible_article_row(conn, article_id, user_id) is None:
            return None
        rows = conn.execute(
            """
            SELECT id, user_id, article_id, highlighted_text, offset_chars, note, created_at
            FROM article_highlights
            WHERE user_id = %s AND article_id = %s
            ORDER BY created_at, id
            """,
            (user_id, article_id),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def add_highlight(
    article_id: int,
    user_id: int,
    *,
    highlighted_text: str,
    offset_chars: int = 0,
    note: str | None = None,
) -> dict[str, Any] | None:
    """Create a private highlight for a visible article."""
    clean_text = highlighted_text.strip()
    clean_note = (note or "").strip() or None
    with connect() as conn:
        if get_visible_article_row(conn, article_id, user_id) is None:
            return None
        row = conn.execute(
            """
            INSERT INTO article_highlights
              (user_id, article_id, highlighted_text, offset_chars, note)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, user_id, article_id, highlighted_text, offset_chars, note, created_at
            """,
            (user_id, article_id, clean_text, offset_chars, clean_note),
        ).fetchone()
    return row_to_dict(row)


def delete_highlight(article_id: int, user_id: int, highlight_id: int) -> bool | None:
    """Delete one private highlight for a visible article."""
    with connect() as conn:
        if get_visible_article_row(conn, article_id, user_id) is None:
            return None
        cursor = conn.execute(
            """
            DELETE FROM article_highlights
            WHERE id = %s AND user_id = %s AND article_id = %s
            """,
            (highlight_id, user_id, article_id),
        )
        return bool(cursor.rowcount > 0)
