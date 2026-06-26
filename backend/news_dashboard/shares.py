"""In-platform article sharing between users.

Lets a user send a news article to another platform user.  The recipient sees
the shared article in a "Shared with me" inbox and (optionally) gets a web-push
notification.

Runtime SQL uses psycopg %s parameter style. No SQLite fallback.
"""

from __future__ import annotations

import logging
from typing import Any

from news_dashboard.db import connect, row_to_dict

logger = logging.getLogger(__name__)


class ShareError(RuntimeError):
    """Raised when a share cannot be created (unknown article/recipient)."""


def shareable_users(current_user_id: int) -> list[dict[str, Any]]:
    """Return platform users the current user can share with (everyone else)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, username, email FROM users WHERE id <> %s ORDER BY username",
            (current_user_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def share_article(
    *,
    article_id: int,
    from_user_id: int,
    to_user_id: int,
    note: str | None = None,
) -> dict[str, Any]:
    """Create a share row. Returns the inserted record.

    Raises ShareError if the article or recipient does not exist, or if the
    sender tries to share with themselves.
    """
    if from_user_id == to_user_id:
        msg = "Cannot share an article with yourself"
        raise ShareError(msg)

    clean_note = (note or "").strip() or None
    with connect() as conn:
        if conn.execute("SELECT 1 FROM articles WHERE id = %s", (article_id,)).fetchone() is None:
            msg = f"Article {article_id} not found"
            raise ShareError(msg)
        if conn.execute("SELECT 1 FROM users WHERE id = %s", (to_user_id,)).fetchone() is None:
            msg = f"Recipient user {to_user_id} not found"
            raise ShareError(msg)
        row = conn.execute(
            """
            INSERT INTO article_shares (article_id, from_user_id, to_user_id, note)
            VALUES (%s, %s, %s, %s)
            RETURNING id, article_id, from_user_id, to_user_id, note, created_at, read_at
            """,
            (article_id, from_user_id, to_user_id, clean_note),
        ).fetchone()
    return row_to_dict(row)


def list_received_shares(user_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
    """Return shares received by a user, newest first, with article + sender info."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.note, s.created_at, s.read_at,
                   s.from_user_id, u.username AS from_username,
                   a.id AS article_id, a.title AS article_title,
                   a.url AS article_url, a.source_name AS article_source_name,
                   a.summary AS article_summary
            FROM article_shares s
            JOIN users u ON u.id = s.from_user_id
            JOIN articles a ON a.id = s.article_id
            WHERE s.to_user_id = %s
            ORDER BY s.created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def mark_share_read(share_id: int, user_id: int) -> bool:
    """Mark a received share as read. Returns True if a row was updated."""
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE article_shares
            SET read_at = NOW()
            WHERE id = %s AND to_user_id = %s AND read_at IS NULL
            """,
            (share_id, user_id),
        )
        return bool(cursor.rowcount > 0)


def unread_share_count(user_id: int) -> int:
    """Return the number of unread shares for a user."""
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM article_shares WHERE to_user_id = %s AND read_at IS NULL",
            (user_id,),
        ).fetchone()
        return int(row_to_dict(row)["n"])
