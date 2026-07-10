"""Business logic for article mutations owned by the HTTP domain."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from news_dashboard.body_fetch import get_article
from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.ingest.service import now_iso
from news_dashboard.url_safety import validate_server_fetch_url

logger = logging.getLogger(__name__)


def embed_article_background(article_id: int) -> None:
    """Generate an embedding after a state change, tolerating optional-service errors."""
    try:
        from news_dashboard.embeddings import ensure_article_embedded

        ensure_article_embedded(article_id)
    except Exception:
        logger.debug("Background embedding skipped for article %d", article_id, exc_info=True)


def save_shared_url(
    user_id: int,
    *,
    url: str,
    title: str | None,
    text: str | None,
) -> dict[str, Any]:
    """Upsert an operating-system shared URL and place it in the user's Today list."""
    validate_server_fetch_url(url)
    init_db()
    parsed = urlparse(url)
    source_name = parsed.netloc or "Shared link"
    source_slug = "share-target"
    article_title = title or text or url
    summary = text if text and text != article_title else ""
    ts = now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, enabled, priority)
            VALUES (%s, 'Shared Links', 'https://example.invalid/share-target', 'shared',
                    'share_target', true, 50)
            ON CONFLICT (slug) DO NOTHING
            """,
            (source_slug,),
        )
        row = conn.execute("SELECT * FROM articles WHERE url = %s", (url,)).fetchone()
        if row is None:
            row = conn.execute(
                """
                INSERT INTO articles(
                  url, canonical_url, title, source_slug, source_name, category, kind,
                  published_at, summary, reason, importance_score, tags, discovered_at, updated_at
                ) VALUES (
                  %s, %s, %s, %s, %s, 'shared', 'share_target',
                  %s, %s, 'Saved from the operating system share sheet', 50, '', %s, %s
                )
                RETURNING *
                """,
                (url, url, article_title, source_slug, source_name, ts, summary, ts, ts),
            ).fetchone()
        article = row_to_dict(row)
        conn.execute(
            """
            INSERT INTO user_article_state(user_id, article_id, state, updated_at)
            VALUES (%s, %s, 'today', %s)
            ON CONFLICT (user_id, article_id) DO UPDATE
               SET state = CASE
                     WHEN user_article_state.state IN ('archived', 'skipped') THEN 'today'
                     ELSE user_article_state.state
                   END,
                   restored_at = CASE
                     WHEN user_article_state.state IN ('archived', 'skipped')
                     THEN EXCLUDED.updated_at
                     ELSE user_article_state.restored_at
                   END,
                   updated_at = EXCLUDED.updated_at
            """,
            (user_id, article["id"], ts),
        )
    return get_article(int(article["id"]), user_id=user_id) or article
