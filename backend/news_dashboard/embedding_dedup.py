"""Post-ingest embedding-similarity dedup pass.

Ingest-time dedup (``news_dashboard.ingest._find_canonical``) only catches
exact canonical-URL matches and fuzzy *title* similarity. The same story
covered under a different headline (vendor blog post vs. HN thread vs. news
write-up) slips through that check and shows up as separate inbox items.

This module adds a second, scheduled dedup pass that compares article
*embeddings* instead of titles: any two recent articles whose embeddings are
cosine-similar above :data:`DEDUP_EMBED_THRESHOLD` are merged using the same
canonical/duplicate shape as the ingest-time path (older article stays
canonical; newer becomes ``state='archived'`` with ``canonical_id`` set).

The threshold is deliberately much stricter than the Topic Map's clustering
threshold (:data:`news_dashboard.insights._CLUSTER_THRESHOLD`, 0.72) — that
one groups *related* stories for the Topic Map UI, whereas this one merges
*duplicate* coverage of the same story, so it must be much more conservative
to avoid clobbering distinct-but-related articles.

Only articles that are still untriaged (``today``) for *every* user are
eligible to be merged, so a merge can never silently destroy someone's triage
state (their Today/Later/Done/Skipped/Archived placement). Source-visibility
rules mirror ``_find_canonical`` exactly: a global source may only merge
against other global articles; a private source may merge against global
articles or other articles owned by the same user, never another user's
private articles.

The whole pass is inert (a clean no-op, no alarming logs) when embedding
credentials are not configured, mirroring the guard used by
``embeddings.embed_all_eligible`` (FREE_LLM_API_KEY / OPENAI_API_KEY).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from news_dashboard.db import connect, init_db
from news_dashboard.embeddings import (
    MissingAICredentialsError,
    _embed,
    embedding_text,
    vector_literal,
)

logger = logging.getLogger(__name__)

# Cosine-similarity threshold above which two recent articles are considered
# duplicate coverage of the same story and merged. Stricter than the Topic
# Map's _CLUSTER_THRESHOLD (0.72), which groups *related* stories, not
# duplicates.
DEDUP_EMBED_THRESHOLD = float(os.getenv("DEDUP_EMBED_THRESHOLD", "0.90"))

# Only consider articles discovered within this window, matching the
# ingest-time fuzzy-title dedup window (_find_canonical).
_DEDUP_WINDOW_DAYS = 7

# Cap the number of articles embedded per run to bound API cost, mirroring
# the spirit of ingest.py's _MAX_SNIPPET_FETCHES_PER_RUN page-fetch cap.
_MAX_EMBED_PER_RUN = 200


def _credentials_configured() -> bool:
    """Return True when embedding credentials are configured.

    Mirrors the guard embed_all_eligible/_embed rely on (FREE_LLM_API_KEY or
    OPENAI_API_KEY) without actually calling out to the provider.
    """
    return bool(os.getenv("FREE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _embed_recent_eligible(db_path: Any, cutoff: str) -> int:
    """Embed recent articles missing an embedding, capped at _MAX_EMBED_PER_RUN.

    Scoped to articles discovered within the dedup window (rather than
    reusing embed_all_eligible's whole-archive query) and capped per run so a
    burst of new articles can never trigger an unbounded number of embedding
    API calls in a single scheduler tick.
    """
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, title, summary, reason, tags FROM articles
            WHERE discovered_at >= %s
              AND canonical_id IS NULL
              AND embedding_vec IS NULL
            ORDER BY discovered_at DESC
            LIMIT %s
            """,
            (cutoff, _MAX_EMBED_PER_RUN),
        ).fetchall()

    embedded = 0
    for row in rows:
        text = embedding_text(row["title"], row["summary"], row["reason"], row["tags"])
        if not text:
            continue
        vector = _embed(text)
        with connect(db_path) as conn:
            conn.execute(
                "UPDATE articles SET embedding_vec=%s::vector WHERE id=%s",
                (vector_literal(vector), row["id"]),
            )
        embedded += 1
    return embedded


def _find_embedding_dedup_candidates(conn: Any, cutoff: str) -> list[dict[str, Any]]:
    """Return pairs of recent, still-canonical articles above the merge threshold.

    Uses a self-join over ``articles`` filtered to the discovery window and
    ranks by the pgvector ``<=>`` cosine-distance operator (1 - cosine
    distance = cosine similarity) so the pairwise comparison happens in SQL
    rather than in a Python loop over all pairs.

    Only pairs where:
      - both articles are still canonical (``canonical_id IS NULL``)
      - both are still ``state = 'today'`` (untouched by ingest-time dedup)
      - neither has been triaged (state changed) by any user
      - source-visibility rules from ``_find_canonical`` are respected
    are returned, ordered so the newer article is always ``dup`` and the
    older is always ``canonical``.
    """
    rows = conn.execute(
        """
        SELECT dup.id AS dup_id, canon.id AS canonical_id,
               1 - (dup.embedding_vec <=> canon.embedding_vec) AS similarity
        FROM articles dup
        JOIN articles canon
          ON canon.id != dup.id
         AND canon.discovered_at <= dup.discovered_at
         AND (canon.discovered_at < dup.discovered_at OR canon.id < dup.id)
        JOIN sources dup_src ON dup_src.slug = dup.source_slug
        JOIN sources canon_src ON canon_src.slug = canon.source_slug
        WHERE dup.discovered_at >= %(cutoff)s
          AND canon.discovered_at >= %(cutoff)s
          AND dup.canonical_id IS NULL
          AND canon.canonical_id IS NULL
          AND dup.state = 'today'
          AND canon.state = 'today'
          AND dup.embedding_vec IS NOT NULL
          AND canon.embedding_vec IS NOT NULL
          AND (
            (dup_src.owner_user_id IS NULL AND canon_src.owner_user_id IS NULL)
            OR (dup_src.owner_user_id IS NOT NULL
                AND (canon_src.owner_user_id IS NULL
                     OR canon_src.owner_user_id = dup_src.owner_user_id))
          )
          AND 1 - (dup.embedding_vec <=> canon.embedding_vec) >= %(threshold)s
          AND NOT EXISTS (
            SELECT 1 FROM user_article_state uas
             WHERE uas.article_id IN (dup.id, canon.id) AND uas.state != 'today'
          )
        ORDER BY dup.discovered_at DESC, similarity DESC
        """,
        {"cutoff": cutoff, "threshold": DEDUP_EMBED_THRESHOLD},
    ).fetchall()
    return [dict(row) for row in rows]


def _merge_duplicate(conn: Any, dup_id: int, canonical_id: int, now: str) -> None:
    """Merge ``dup_id`` into ``canonical_id`` using the ingest-time dedup shape.

    Same shape as the ingest-time merge path (ingest.py `_ingest_source`):
    the duplicate becomes state/status='archived' with canonical_id set; the
    canonical's updated_at is bumped so it re-sorts to the top. Re-checks
    canonical_id IS NULL on both sides so a merge computed earlier in this
    same run (now stale) is never double-applied.
    """
    updated = conn.execute(
        """
        UPDATE articles
           SET state = 'archived', status = 'archived', canonical_id = %s, updated_at = %s
         WHERE id = %s AND canonical_id IS NULL
        """,
        (canonical_id, now, dup_id),
    )
    if updated.rowcount == 0:
        return
    conn.execute(
        "UPDATE articles SET updated_at = %s WHERE id = %s AND canonical_id IS NULL",
        (now, canonical_id),
    )


def run_embedding_dedup(db_path: Any = None) -> dict[str, int]:
    """Run the post-ingest embedding-similarity dedup pass.

    Steps:
      1. No-op cleanly (info log only) if embedding credentials are absent.
      2. Embed any eligible recent articles still missing an embedding,
         capped at _MAX_EMBED_PER_RUN per run to bound API cost.
      3. Find candidate duplicate pairs within the last _DEDUP_WINDOW_DAYS
         days via a SQL self-join on the pgvector `<=>` operator.
      4. Merge each pair (newer article archived as a duplicate of the
         older), skipping any pair that's gone stale in-run (e.g. the
         canonical was itself merged into something else already).

    Returns a summary dict: {"embedded": int, "merged": int}.
    """
    if not _credentials_configured():
        logger.info("Embedding dedup skipped: no embedding credentials configured.")
        return {"embedded": 0, "merged": 0}

    init_db(db_path)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=_DEDUP_WINDOW_DAYS)).isoformat()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    embedded = 0
    try:
        embedded = _embed_recent_eligible(db_path, cutoff)
    except MissingAICredentialsError:
        logger.info("Embedding dedup skipped: no embedding credentials configured.")
        return {"embedded": 0, "merged": 0}

    merged = 0
    with connect(db_path) as conn:
        candidates = _find_embedding_dedup_candidates(conn, cutoff)
        for candidate in candidates:
            _merge_duplicate(conn, candidate["dup_id"], candidate["canonical_id"], now)
            merged += 1

    logger.info("Embedding dedup complete: %d embedded, %d merged", embedded, merged)
    return {"embedded": embedded, "merged": merged}
