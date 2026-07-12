"""Restore a personal archive JSON export back into the authenticated user's data.

Counterpart to `news_dashboard.export.assemble_user_export`. Only the archive
schema produced by that module is accepted, and only for the authenticated
user: this is a personal restore, not a cross-instance sync tool.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from psycopg.types.json import Jsonb

from news_dashboard.db import connect
from news_dashboard.export import SCHEMA_VERSION
from news_dashboard.sources.models import USER_CREATED_SOURCE_KINDS
from news_dashboard.url_safety import UnsafeUrlError, validate_server_fetch_url

logger = logging.getLogger(__name__)

# Generous ceilings on object counts so a hostile or corrupted archive can't
# make a restore run for an unbounded amount of time or memory.
MAX_IMPORT_ARTICLES = 20_000
MAX_IMPORT_BRIEFINGS = 5_000
MAX_IMPORT_AI_MEMORIES = 5_000
MAX_IMPORT_AI_MEMORY_EVENTS = 20_000
MAX_IMPORT_SOURCE_SUBSCRIPTIONS = 2_000

_VALID_ARTICLE_STATES = frozenset({"today", "done", "skipped", "archived", "later"})
_VALID_RECAP_DAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})


class ArchiveImportError(ValueError):
    """Raised when an uploaded archive fails validation before any write happens."""


def validate_archive(payload: Any) -> None:
    """Raise ArchiveImportError if the payload isn't a restorable archive."""
    if not isinstance(payload, dict):
        msg = "archive must be a JSON object"
        raise ArchiveImportError(msg)

    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        msg = f"unsupported schema_version {schema_version!r} (expected {SCHEMA_VERSION})"
        raise ArchiveImportError(msg)

    for key, limit in (
        ("articles", MAX_IMPORT_ARTICLES),
        ("briefings", MAX_IMPORT_BRIEFINGS),
        ("ai_memories", MAX_IMPORT_AI_MEMORIES),
        ("ai_memory_events", MAX_IMPORT_AI_MEMORY_EVENTS),
        ("source_subscriptions", MAX_IMPORT_SOURCE_SUBSCRIPTIONS),
    ):
        value = payload.get(key, [])
        if value is None:
            continue
        if not isinstance(value, list):
            msg = f"{key!r} must be a list"
            raise ArchiveImportError(msg)
        if len(value) > limit:
            msg = f"archive has too many {key} entries (max {limit})"
            raise ArchiveImportError(msg)

    preferences = payload.get("preferences")
    if preferences is not None and not isinstance(preferences, dict):
        msg = "'preferences' must be an object"
        raise ArchiveImportError(msg)


def _upsert_article_state(  # noqa: PLR0913
    conn: Any,
    user_id: int,
    article_id: int,
    *,
    state: str,
    starred: bool,
    done_at: str | None,
    starred_at: str | None,
    skipped_at: str | None,
    archived_at: str | None,
    later_until: str | None,
    restored_at: str | None,
    updated_at: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO user_article_state(
          user_id, article_id, state, starred,
          done_at, starred_at, skipped_at, archived_at, later_until, restored_at, updated_at
        ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))
        ON CONFLICT(user_id, article_id) DO UPDATE SET
          state = excluded.state,
          starred = excluded.starred,
          done_at = COALESCE(excluded.done_at, user_article_state.done_at),
          starred_at = COALESCE(excluded.starred_at, user_article_state.starred_at),
          skipped_at = COALESCE(excluded.skipped_at, user_article_state.skipped_at),
          archived_at = COALESCE(excluded.archived_at, user_article_state.archived_at),
          later_until = COALESCE(excluded.later_until, user_article_state.later_until),
          restored_at = COALESCE(excluded.restored_at, user_article_state.restored_at),
          updated_at = excluded.updated_at
        """,
        (
            user_id,
            article_id,
            state,
            starred,
            done_at,
            starred_at,
            skipped_at,
            archived_at,
            later_until,
            restored_at,
            updated_at,
        ),
    )


def _resolve_article_id(conn: Any, item: dict[str, Any]) -> int | None:
    canonical_url = item.get("canonical_url")
    if not canonical_url or not isinstance(canonical_url, str):
        return None

    row = conn.execute(
        "SELECT id FROM articles WHERE canonical_url = %s ORDER BY id ASC LIMIT 1",
        (canonical_url,),
    ).fetchone()
    if row is not None:
        return int(row["id"])

    title = item.get("title")
    source_slug = item.get("source_slug")
    source_name = item.get("source_name")
    category = item.get("category")
    kind = item.get("kind")
    required = (title, source_slug, source_name, category, kind)
    if not all(isinstance(v, str) and v.strip() for v in required):
        return None

    source_exists = conn.execute("SELECT 1 FROM sources WHERE slug = %s", (source_slug,)).fetchone()
    if source_exists is None:
        return None

    row = conn.execute(
        """
        INSERT INTO articles(url, canonical_url, title, source_slug, source_name, category, kind)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url) DO UPDATE SET url = articles.url
        RETURNING id
        """,
        (canonical_url, canonical_url, title, source_slug, source_name, category, kind),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def _restore_articles(conn: Any, user_id: int, articles: list[Any]) -> dict[str, int]:
    counts = {"added": 0, "updated": 0, "skipped": 0}
    for item in articles:
        if not isinstance(item, dict):
            counts["skipped"] += 1
            continue
        try:
            with conn.transaction():
                article_id = _resolve_article_id(conn, item)
                if article_id is None:
                    counts["skipped"] += 1
                    continue

                raw_state = item.get("state")
                state: str = raw_state if isinstance(raw_state, str) else "today"
                if state not in _VALID_ARTICLE_STATES:
                    state = "today"

                existing = conn.execute(
                    "SELECT 1 FROM user_article_state WHERE user_id = %s AND article_id = %s",
                    (user_id, article_id),
                ).fetchone()

                _upsert_article_state(
                    conn,
                    user_id,
                    article_id,
                    state=state,
                    starred=bool(item.get("starred", False)),
                    done_at=item.get("done_at"),
                    starred_at=item.get("starred_at"),
                    skipped_at=item.get("skipped_at"),
                    archived_at=item.get("archived_at"),
                    later_until=item.get("later_until"),
                    restored_at=item.get("restored_at"),
                    updated_at=item.get("updated_at"),
                )
                counts["updated" if existing is not None else "added"] += 1
        except Exception:
            logger.exception("Failed to restore archived article state")
            counts["skipped"] += 1
    return counts


def _restore_cited_articles(conn: Any, briefing_id: int, cited_articles: Any) -> None:
    if not isinstance(cited_articles, list):
        return
    for cited in cited_articles:
        if not isinstance(cited, dict):
            continue
        canonical_url = cited.get("canonical_url")
        if not canonical_url or not isinstance(canonical_url, str):
            continue
        row = conn.execute(
            "SELECT id FROM articles WHERE canonical_url = %s", (canonical_url,)
        ).fetchone()
        if row is None:
            continue
        conn.execute(
            """
            INSERT INTO briefing_articles(briefing_id, article_id)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
            """,
            (briefing_id, int(row["id"])),
        )


def _restore_briefings(conn: Any, user_id: int, briefings: list[Any]) -> dict[str, int]:
    counts = {"added": 0, "updated": 0, "skipped": 0}
    for item in briefings:
        if not isinstance(item, dict):
            counts["skipped"] += 1
            continue
        created_at = item.get("created_at")
        if not created_at or not isinstance(created_at, str):
            counts["skipped"] += 1
            continue
        title = item.get("title")

        try:
            with conn.transaction():
                existing = conn.execute(
                    """
                    SELECT id FROM briefings
                    WHERE user_id = %s AND created_at = %s
                      AND COALESCE(title, '') = COALESCE(%s, '')
                    """,
                    (user_id, created_at, title),
                ).fetchone()

                if existing is not None:
                    briefing_id = int(existing["id"])
                    conn.execute(
                        """
                        UPDATE briefings SET
                          scope = %s, since_at = %s, until_at = %s, status = %s,
                          summary = %s, focus_prompt = %s, model = %s
                        WHERE id = %s
                        """,
                        (
                            item.get("scope") or "since_last_briefing",
                            item.get("since_at"),
                            item.get("until_at"),
                            item.get("status") or "complete",
                            item.get("summary"),
                            item.get("focus_prompt"),
                            item.get("model"),
                            briefing_id,
                        ),
                    )
                    counts["updated"] += 1
                else:
                    row = conn.execute(
                        """
                        INSERT INTO briefings(
                          user_id, created_at, scope, since_at, until_at, status,
                          title, summary, focus_prompt, model
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            user_id,
                            created_at,
                            item.get("scope") or "since_last_briefing",
                            item.get("since_at"),
                            item.get("until_at"),
                            item.get("status") or "complete",
                            title,
                            item.get("summary"),
                            item.get("focus_prompt"),
                            item.get("model"),
                        ),
                    ).fetchone()
                    if row is None:
                        counts["skipped"] += 1
                        continue
                    briefing_id = int(row["id"])
                    counts["added"] += 1

                _restore_cited_articles(conn, briefing_id, item.get("cited_articles"))
        except Exception:
            logger.exception("Failed to restore archived briefing")
            counts["skipped"] += 1
    return counts


def _restore_ai_memories(conn: Any, user_id: int, memories: list[Any]) -> dict[str, int]:
    counts = {"added": 0, "updated": 0, "skipped": 0}
    for item in memories:
        if not isinstance(item, dict):
            counts["skipped"] += 1
            continue
        content = item.get("content")
        source = item.get("source")
        if not isinstance(content, str) or not content.strip():
            counts["skipped"] += 1
            continue
        if not isinstance(source, str) or not source.strip():
            counts["skipped"] += 1
            continue

        memory_type = item.get("memory_type") or "preference"
        confidence = item.get("confidence")
        confidence = float(confidence) if isinstance(confidence, (int, float)) else 1.0
        confidence = min(1.0, max(0.0, confidence))
        active = bool(item.get("active", True))

        try:
            with conn.transaction():
                existing = conn.execute(
                    """
                    SELECT id FROM user_ai_memories
                    WHERE user_id = %s AND content = %s AND source = %s
                    """,
                    (user_id, content, source),
                ).fetchone()
                if existing is not None:
                    conn.execute(
                        """
                        UPDATE user_ai_memories
                        SET memory_type = %s, confidence = %s, active = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (memory_type, confidence, active, existing["id"]),
                    )
                    counts["updated"] += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO user_ai_memories(
                          user_id, memory_type, content, source, confidence, active
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (user_id, memory_type, content, source, confidence, active),
                    )
                    counts["added"] += 1
        except Exception:
            logger.exception("Failed to restore archived AI memory")
            counts["skipped"] += 1
    return counts


def _restore_ai_memory_events(conn: Any, user_id: int, events: list[Any]) -> dict[str, int]:
    counts = {"added": 0, "skipped": 0}
    for item in events:
        if not isinstance(item, dict):
            counts["skipped"] += 1
            continue
        event_type = item.get("event_type")
        source = item.get("source")
        content = item.get("content")
        created_at = item.get("created_at")
        required = (event_type, source, content, created_at)
        if not all(isinstance(v, str) and v.strip() for v in required):
            counts["skipped"] += 1
            continue

        try:
            with conn.transaction():
                existing = conn.execute(
                    """
                    SELECT 1 FROM user_ai_memory_events
                    WHERE user_id = %s AND event_type = %s AND source = %s
                      AND content = %s AND created_at = %s
                    """,
                    (user_id, event_type, source, content, created_at),
                ).fetchone()
                if existing is not None:
                    counts["skipped"] += 1
                    continue
                conn.execute(
                    """
                    INSERT INTO user_ai_memory_events(
                      user_id, event_type, source, content, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, event_type, source, content, created_at),
                )
                counts["added"] += 1
        except Exception:
            logger.exception("Failed to restore archived AI memory event")
            counts["skipped"] += 1
    return counts


def _restore_global_source_subscription(
    conn: Any, user_id: int, slug: str, *, enabled: bool
) -> str | None:
    """Restore subscribed/unsubscribed state for a global source. Returns 'added'/'updated'/None."""
    exists = conn.execute(
        "SELECT 1 FROM sources WHERE slug = %s AND owner_user_id IS NULL", (slug,)
    ).fetchone()
    if exists is None:
        return None

    existing = conn.execute(
        "SELECT 1 FROM user_sources WHERE user_id = %s AND source_slug = %s",
        (user_id, slug),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO user_sources(user_id, source_slug, enabled)
        VALUES (%s, %s, %s)
        ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = excluded.enabled
        """,
        (user_id, slug, enabled),
    )
    return "updated" if existing is not None else "added"


def _validate_private_source_fields(item: dict[str, Any]) -> tuple[str, str, str, str, str] | None:
    slug = item.get("slug")
    name = item.get("name")
    url = item.get("url")
    category = item.get("category")
    kind = item.get("kind")
    required = (slug, name, url, category, kind)
    if not all(isinstance(v, str) and v.strip() for v in required):
        return None
    slug, name, url, category, kind = cast("tuple[str, str, str, str, str]", required)
    if kind not in USER_CREATED_SOURCE_KINDS:
        return None
    try:
        validate_server_fetch_url(url)
    except UnsafeUrlError:
        return None
    return slug, name, url, category, kind


def _restore_private_source(conn: Any, user_id: int, item: dict[str, Any]) -> str | None:
    """Restore a user-owned private source. Returns 'added'/'updated'/None (skipped)."""
    fields = _validate_private_source_fields(item)
    if fields is None:
        return None
    slug, name, url, category, kind = fields
    enabled = bool(item.get("subscribed", True))

    existing = conn.execute("SELECT owner_user_id FROM sources WHERE slug = %s", (slug,)).fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
            VALUES (%s, %s, %s, %s, %s, 0, %s, %s)
            """,
            (slug, name, url, category, kind, enabled, user_id),
        )
        return "added"
    if existing["owner_user_id"] != user_id:
        # Never overwrite a global source or another user's private source.
        return None
    conn.execute(
        """
        UPDATE sources SET name = %s, url = %s, category = %s, kind = %s, enabled = %s
        WHERE slug = %s
        """,
        (name, url, category, kind, enabled, slug),
    )
    return "updated"


def _restore_source_subscriptions(
    conn: Any, user_id: int, subscriptions: list[Any]
) -> dict[str, int]:
    counts = {"added": 0, "updated": 0, "skipped": 0}
    for item in subscriptions:
        if not isinstance(item, dict):
            counts["skipped"] += 1
            continue
        try:
            with conn.transaction():
                if item.get("private"):
                    outcome = _restore_private_source(conn, user_id, item)
                else:
                    slug = item.get("slug")
                    if not isinstance(slug, str) or not slug.strip():
                        outcome = None
                    else:
                        outcome = _restore_global_source_subscription(
                            conn, user_id, slug, enabled=bool(item.get("subscribed", True))
                        )
                counts[outcome or "skipped"] += 1
        except Exception:
            logger.exception("Failed to restore archived source subscription")
            counts["skipped"] += 1
    return counts


def _restore_recommendation_preferences(conn: Any, user_id: int, data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    raw_weights = data.get("category_weights")
    if not isinstance(raw_weights, dict):
        raw_weights = {}
    weights = {
        str(category).strip().lower(): min(3.0, max(0.0, float(weight)))
        for category, weight in raw_weights.items()
        if str(category).strip() and isinstance(weight, (int, float))
    }
    novelty = data.get("novelty_weight")
    novelty = min(3.0, max(0.0, float(novelty))) if isinstance(novelty, (int, float)) else 1.0

    conn.execute(
        """
        INSERT INTO user_settings(user_id, category_weights, novelty_weight)
        VALUES (%s, %s::jsonb, %s)
        ON CONFLICT(user_id) DO UPDATE SET
          category_weights = excluded.category_weights,
          novelty_weight = excluded.novelty_weight,
          updated_at = NOW()
        """,
        (user_id, json.dumps(weights), novelty),
    )
    conn.execute(
        "UPDATE user_article_recommendations SET stale = TRUE WHERE user_id = %s",
        (user_id,),
    )
    return True


def _restore_onboarding(conn: Any, user_id: int, data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    raw_interests = data.get("interests")
    interests = [str(i) for i in raw_interests] if isinstance(raw_interests, list) else []
    completed_at = data.get("completed_at")
    completed = isinstance(completed_at, str) and bool(completed_at.strip())

    conn.execute(
        """
        INSERT INTO user_interest_profiles(user_id, interests, completed_at, updated_at)
        VALUES (%s, %s, CASE WHEN %s THEN NOW() ELSE NULL END, NOW())
        ON CONFLICT(user_id) DO UPDATE SET
          interests = excluded.interests,
          completed_at = excluded.completed_at,
          updated_at = NOW()
        """,
        (user_id, Jsonb(interests), completed),
    )
    return True


def _restore_notification_settings(conn: Any, user_id: int, data: Any) -> bool:
    if not isinstance(data, dict):
        return False

    updates: dict[str, Any] = {}
    briefing_time = data.get("briefing_time")
    if isinstance(briefing_time, str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", briefing_time):
        updates["briefing_time"] = briefing_time
    briefing_timezone = data.get("briefing_timezone")
    if isinstance(briefing_timezone, str) and briefing_timezone.strip():
        try:
            ZoneInfo(briefing_timezone)
        except (ZoneInfoNotFoundError, KeyError):
            pass
        else:
            updates["briefing_timezone"] = briefing_timezone
    if isinstance(data.get("push_enabled"), bool):
        updates["briefing_push_enabled"] = data["push_enabled"]
    if isinstance(data.get("recap_enabled"), bool):
        updates["recap_enabled"] = data["recap_enabled"]
    recap_day = data.get("recap_day")
    if isinstance(recap_day, str) and recap_day in _VALID_RECAP_DAYS:
        updates["recap_day"] = recap_day
    if isinstance(data.get("analytics_enabled"), bool):
        updates["analytics_enabled"] = data["analytics_enabled"]

    if not updates:
        return False

    set_clauses = ", ".join(f"{key} = %s" for key in updates)
    conn.execute(
        f"UPDATE users SET {set_clauses} WHERE id = %s",
        [*updates.values(), user_id],
    )
    return True


def _restore_preferences(conn: Any, user_id: int, preferences: Any) -> dict[str, int]:
    counts = {"added": 0, "updated": 0, "skipped": 0}
    if not isinstance(preferences, dict):
        return counts

    sections = (
        _restore_recommendation_preferences(conn, user_id, preferences.get("recommendations")),
        _restore_onboarding(conn, user_id, preferences.get("onboarding")),
        _restore_notification_settings(conn, user_id, preferences.get("notifications")),
    )
    for restored in sections:
        counts["updated" if restored else "skipped"] += 1
    return counts


def restore_user_archive(
    user_id: int,
    payload: dict[str, Any],
    database_url: str | None = None,
) -> dict[str, dict[str, int]]:
    """Restore a personal archive for `user_id`, returning per-section counts.

    Idempotent: re-importing the same archive updates/keeps existing restored
    state rather than duplicating rows, for object types with a stable
    identity (article canonical_url, briefing created_at+title, AI memory
    content+source, source subscription slug, preferences per user). Only
    ever writes data scoped to `user_id`.
    """
    validate_archive(payload)

    with connect(database_url=database_url) as conn:
        articles = _restore_articles(conn, user_id, payload.get("articles") or [])
        briefings = _restore_briefings(conn, user_id, payload.get("briefings") or [])
        ai_memories = _restore_ai_memories(conn, user_id, payload.get("ai_memories") or [])
        ai_memory_events = _restore_ai_memory_events(
            conn, user_id, payload.get("ai_memory_events") or []
        )
        source_subscriptions = _restore_source_subscriptions(
            conn, user_id, payload.get("source_subscriptions") or []
        )
        preferences = _restore_preferences(conn, user_id, payload.get("preferences"))

    return {
        "articles": articles,
        "briefings": briefings,
        "ai_memories": ai_memories,
        "ai_memory_events": ai_memory_events,
        "source_subscriptions": source_subscriptions,
        "preferences": preferences,
    }
