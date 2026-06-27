"""In-platform article sharing between users.

Lets a user send a news article to another platform user.  The recipient sees
the shared article in a "Shared with me" inbox and (optionally) gets a web-push
notification.

Runtime SQL uses psycopg %s parameter style. No SQLite fallback.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from news_dashboard.db import connect, row_to_dict

logger = logging.getLogger(__name__)

DEFAULT_SHARE_MODEL = "gpt-4o-mini"


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
            RETURNING id, article_id, from_user_id, to_user_id, note,
                      context_summary, created_at, read_at
            """,
            (article_id, from_user_id, to_user_id, clean_note),
        ).fetchone()
    return row_to_dict(row)


def list_received_shares(user_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
    """Return shares received by a user, newest first, with article + sender info."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.note, s.context_summary, s.created_at, s.read_at,
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
        shares = [row_to_dict(r) for r in rows]
    for share in shares:
        share["annotations"] = list_annotations(int(share["id"]))
        share["messages"] = list_messages(int(share["id"]))
    return shares


def get_share(share_id: int, user_id: int) -> dict[str, Any] | None:
    """Return a single share visible to user_id (sender or recipient), with full detail."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT s.id, s.note, s.context_summary, s.created_at, s.read_at,
                   s.from_user_id, u.username AS from_username,
                   a.id AS article_id, a.title AS article_title,
                   a.url AS article_url, a.source_name AS article_source_name,
                   a.summary AS article_summary
            FROM article_shares s
            JOIN users u ON u.id = s.from_user_id
            JOIN articles a ON a.id = s.article_id
            WHERE s.id = %s AND (s.to_user_id = %s OR s.from_user_id = %s)
            """,
            (share_id, user_id, user_id),
        ).fetchone()
    if row is None:
        return None
    share = row_to_dict(row)
    share["annotations"] = list_annotations(share_id)
    share["messages"] = list_messages(share_id)
    return share


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


# ── Annotations ──────────────────────────────────────────────────────────────


def add_annotation(
    share_id: int,
    *,
    highlighted_text: str,
    offset_chars: int = 0,
    note: str | None = None,
) -> dict[str, Any]:
    """Append a highlight annotation to a share."""
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO share_annotations (share_id, highlighted_text, offset_chars, note)
            VALUES (%s, %s, %s, %s)
            RETURNING id, share_id, highlighted_text, offset_chars, note, created_at
            """,
            (share_id, highlighted_text, offset_chars, note),
        ).fetchone()
    return row_to_dict(row)


def list_annotations(share_id: int) -> list[dict[str, Any]]:
    """Return all annotations for a share, oldest first."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, share_id, highlighted_text, offset_chars, note, created_at
            FROM share_annotations
            WHERE share_id = %s
            ORDER BY created_at
            """,
            (share_id,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


# ── Messages (comment thread) ─────────────────────────────────────────────────


def add_message(share_id: int, user_id: int, message: str) -> dict[str, Any]:
    """Append a message to a share's comment thread."""
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO share_messages (share_id, user_id, message)
            VALUES (%s, %s, %s)
            RETURNING id, share_id, user_id, message, created_at
            """,
            (share_id, user_id, message),
        ).fetchone()
    return row_to_dict(row)


def list_messages(share_id: int) -> list[dict[str, Any]]:
    """Return all messages in a share's comment thread, oldest first."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.share_id, m.user_id, u.username, m.message, m.created_at
            FROM share_messages m
            JOIN users u ON u.id = m.user_id
            WHERE m.share_id = %s
            ORDER BY m.created_at
            """,
            (share_id,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


# ── AI context generation ─────────────────────────────────────────────────────


def generate_share_context(share_id: int) -> str | None:
    """Generate and persist a personalised context summary for a share.

    Reads the article content, the sender's annotations, and the recipient's
    recent reading categories, then asks the LLM for a 2-sentence explanation
    of why the highlighted sections matter to the recipient.  The result is
    stored in ``article_shares.context_summary`` and returned.

    Returns None if no API key is configured or if the share doesn't exist.
    """
    api_key = os.getenv("OPENAI_BRIEFING_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("generate_share_context: no OpenAI API key configured, skipping")
        return None

    base_url = os.getenv("OPENAI_BRIEFING_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
    model = os.getenv("OPENAI_BRIEFING_MODEL", DEFAULT_SHARE_MODEL)

    with connect() as conn:
        row = conn.execute(
            """
            SELECT s.id, s.note, s.from_user_id, s.to_user_id,
                   a.title, a.summary, a.body
            FROM article_shares s
            JOIN articles a ON a.id = s.article_id
            WHERE s.id = %s
            """,
            (share_id,),
        ).fetchone()
        if row is None:
            return None
        share_data = row_to_dict(row)

        annotations = list_annotations(share_id)

        # Recipient's top reading categories for personalisation
        recipient_cats = conn.execute(
            """
            SELECT a.category, COUNT(*) AS n
            FROM user_article_state s
            JOIN articles a ON a.id = s.article_id
            WHERE s.user_id = %s AND s.state = 'done'
            GROUP BY a.category
            ORDER BY n DESC
            LIMIT 5
            """,
            (share_data["to_user_id"],),
        ).fetchall()
        top_categories = [r["category"] for r in recipient_cats]

    annotation_text = ""
    if annotations:
        parts = []
        for ann in annotations:
            snippet = ann["highlighted_text"][:200]
            ann_note = f": {ann['note']}" if ann.get("note") else ""
            parts.append(f'- "{snippet}"{ann_note}')
        annotation_text = "\n".join(parts)
    else:
        annotation_text = "(no highlights)"

    sender_note = share_data.get("note") or ""
    article_title = share_data.get("title") or ""
    article_summary = (share_data.get("summary") or share_data.get("body") or "")[:800]
    recipient_interests = ", ".join(top_categories) if top_categories else "general news"

    prompt = (
        f'Article: "{article_title}"\n'
        f"Summary: {article_summary}\n\n"
        f"Sender's note: {sender_note or '(none)'}\n"
        f"Highlighted sections:\n{annotation_text}\n\n"
        f"Recipient's main reading interests: {recipient_interests}\n\n"
        "Write exactly 2 sentences explaining why the sender highlighted these specific "
        "sections and why they are directly relevant to the recipient's interests. "
        "Be specific and personal, not generic."
    )

    from news_dashboard.ai_client import chat_create, get_openai_client

    client = get_openai_client(api_key=api_key, base_url=base_url)
    try:
        completion = chat_create(
            client,
            name="share-context",
            tags=["shares"],
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.7,
        )
        context = completion.choices[0].message.content or ""
        context = context.strip()
    except Exception:
        logger.exception("generate_share_context: LLM call failed for share %d", share_id)
        return None

    with connect() as conn:
        conn.execute(
            "UPDATE article_shares SET context_summary = %s WHERE id = %s",
            (context, share_id),
        )

    return context
