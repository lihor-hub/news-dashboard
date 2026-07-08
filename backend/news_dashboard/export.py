"""Assemble a portable JSON archive of a user's personal reading data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from news_dashboard.db import connect, row_to_dict

SCHEMA_VERSION = 2

# Safe, non-secret user columns. Excludes password_hash and
# podcast_feed_token_version, which are never exported.
_NOTIFICATION_COLS = (
    "briefing_time, briefing_push_enabled, briefing_timezone, recap_enabled, recap_day, "
    "analytics_enabled"
)


def _normalize_timestamps(d: dict[str, Any], columns: tuple[str, ...]) -> None:
    for col in columns:
        val = d.get(col)
        if val is not None and not isinstance(val, str):
            d[col] = val.isoformat()


def _export_articles(conn: Any, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            a.id,
            a.canonical_url,
            a.title,
            a.source_slug,
            a.source_name,
            a.category,
            a.kind,
            a.published_at,
            a.discovered_at,
            a.summary,
            a.reason,
            a.tags,
            uas.state,
            uas.starred,
            uas.done_at,
            uas.starred_at,
            uas.skipped_at,
            uas.archived_at,
            uas.later_until,
            uas.restored_at,
            uas.updated_at
        FROM user_article_state uas
        JOIN articles a ON a.id = uas.article_id
        WHERE uas.user_id = %s
        ORDER BY a.id ASC
        """,
        (user_id,),
    ).fetchall()

    articles: list[dict[str, Any]] = []
    for row in rows:
        d = row_to_dict(row)
        _normalize_timestamps(
            d,
            (
                "done_at",
                "starred_at",
                "skipped_at",
                "archived_at",
                "later_until",
                "restored_at",
                "updated_at",
            ),
        )
        articles.append(d)
    return articles


def _export_briefings(conn: Any, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            b.id,
            b.created_at,
            b.scope,
            b.since_at,
            b.until_at,
            b.status,
            b.title,
            b.summary,
            b.focus_prompt,
            b.model
        FROM briefings b
        WHERE b.user_id = %s
        ORDER BY b.id ASC
        """,
        (user_id,),
    ).fetchall()

    briefings: list[dict[str, Any]] = []
    for brow in rows:
        bd = row_to_dict(brow)
        _normalize_timestamps(bd, ("created_at", "since_at", "until_at"))

        cited_rows = conn.execute(
            """
            SELECT ba.article_id, a.canonical_url
            FROM briefing_articles ba
            JOIN articles a ON a.id = ba.article_id
            WHERE ba.briefing_id = %s
            ORDER BY ba.article_id ASC
            """,
            (bd["id"],),
        ).fetchall()
        bd["cited_articles"] = [
            {"article_id": r["article_id"], "canonical_url": r["canonical_url"]} for r in cited_rows
        ]
        briefings.append(bd)
    return briefings


def _export_ai_memories(conn: Any, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, memory_type, content, source, confidence, active, created_at, updated_at
        FROM user_ai_memories
        WHERE user_id = %s
        ORDER BY id ASC
        """,
        (user_id,),
    ).fetchall()
    memories: list[dict[str, Any]] = []
    for row in rows:
        md = row_to_dict(row)
        _normalize_timestamps(md, ("created_at", "updated_at"))
        memories.append(md)
    return memories


def _export_ai_memory_events(conn: Any, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, memory_id, event_type, source, content, metadata, created_at
        FROM user_ai_memory_events
        WHERE user_id = %s
        ORDER BY id ASC
        """,
        (user_id,),
    ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        ed = row_to_dict(row)
        _normalize_timestamps(ed, ("created_at",))
        events.append(ed)
    return events


def _export_source_subscriptions(conn: Any, user_id: int) -> list[dict[str, Any]]:
    """Return the user's global source subscription state plus owned private sources.

    Other users' private sources are excluded by the owner_user_id scope below.
    """
    rows = conn.execute(
        """
        SELECT s.slug, s.name, s.url, s.category, s.kind, s.owner_user_id,
          CASE WHEN s.owner_user_id IS NULL THEN COALESCE(us.enabled, true)
               ELSE (s.enabled IS TRUE) END AS subscribed
        FROM sources s
        LEFT JOIN user_sources us ON us.source_slug = s.slug AND us.user_id = %s
        WHERE (s.owner_user_id IS NULL OR s.owner_user_id = %s)
          AND s.deleted_at IS NULL
        ORDER BY s.category, s.slug
        """,
        (user_id, user_id),
    ).fetchall()
    subscriptions: list[dict[str, Any]] = []
    for row in rows:
        sd = row_to_dict(row)
        sd["subscribed"] = bool(sd["subscribed"])
        sd["private"] = sd.pop("owner_user_id") is not None
        subscriptions.append(sd)
    return subscriptions


def _export_recommendation_preferences(conn: Any, user_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT category_weights, novelty_weight FROM user_settings WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    if row is None:
        return {"category_weights": {}, "novelty_weight": 1.0}
    return {
        "category_weights": row["category_weights"] or {},
        "novelty_weight": float(row["novelty_weight"] or 1.0),
    }


def _export_onboarding(conn: Any, user_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT interests, completed_at, updated_at FROM user_interest_profiles WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    if row is None:
        return {"interests": [], "completed_at": None, "updated_at": None}
    d = row_to_dict(row)
    _normalize_timestamps(d, ("completed_at", "updated_at"))
    return d


def _export_notification_settings(conn: Any, user_id: int) -> dict[str, Any]:
    row = conn.execute(
        f"SELECT {_NOTIFICATION_COLS} FROM users WHERE id = %s",
        (user_id,),
    ).fetchone()
    if row is None:
        return {
            "briefing_time": "09:00",
            "briefing_timezone": "UTC",
            "push_enabled": False,
            "recap_enabled": True,
            "recap_day": "mon",
            "analytics_enabled": True,
        }
    return {
        "briefing_time": row["briefing_time"] or "09:00",
        "briefing_timezone": row["briefing_timezone"] or "UTC",
        "push_enabled": bool(row["briefing_push_enabled"]),
        "recap_enabled": bool(row["recap_enabled"]),
        "recap_day": row["recap_day"] or "mon",
        "analytics_enabled": bool(row["analytics_enabled"]),
    }


def assemble_user_export(
    user_id: int,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic JSON-serialisable dict of the user's reading archive.

    Includes:
    - articles the user has explicitly interacted with (user_article_state rows),
      joined with article metadata (title, URL, category, summary, tags).
    - user-owned briefings with their cited article IDs.
    - source_subscriptions: the user's enabled/disabled state for global sources,
      plus any private sources the user owns. Other users' private sources are
      never included.
    - preferences: recommendation weights, onboarding interests/completion
      state, and notification settings (briefing time/timezone, push-enabled,
      recap, analytics opt-in).

    Data is ordered by stable keys (id / created_at) so the output is
    deterministic enough for snapshot-style tests.

    No secrets are exported: password hashes, session tokens, OTP hashes, MCP
    API tokens, and raw push-subscription keys are never read here.
    """
    with connect(database_url=database_url) as conn:
        articles = _export_articles(conn, user_id)
        briefings = _export_briefings(conn, user_id)
        memories = _export_ai_memories(conn, user_id)
        memory_events = _export_ai_memory_events(conn, user_id)
        source_subscriptions = _export_source_subscriptions(conn, user_id)
        preferences = {
            "recommendations": _export_recommendation_preferences(conn, user_id),
            "onboarding": _export_onboarding(conn, user_id),
            "notifications": _export_notification_settings(conn, user_id),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "includes_article_bodies": False,
        "articles": articles,
        "briefings": briefings,
        "ai_memories": memories,
        "ai_memory_events": memory_events,
        "source_subscriptions": source_subscriptions,
        "preferences": preferences,
    }
