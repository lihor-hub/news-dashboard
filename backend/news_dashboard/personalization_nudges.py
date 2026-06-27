"""Proactive nudges that suggest disabling noisy sources or topics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db, row_to_dict

_LOW_SIGNAL_MIN_ARTICLES = 30
_LOW_SIGNAL_SKIP_RATE = 0.75
_TOPIC_MIN_ARTICLES = 20
_TOPIC_SKIP_RATE = 0.75
_DEFAULT_COOLDOWN_DAYS = 7
_TOPIC_WEIGHT_REDUCTION = 0.25


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def generate_nudges(
    user_id: int,
    *,
    db_path: Path | str | None = None,
    database_url: str | None = None,
    max_results: int = 1,
) -> list[dict[str, Any]]:
    """Return up to *max_results* actionable nudges for *user_id*.

    Returns a list ordered by skip_rate descending so the noisiest signal
    comes first.  Nudges that are still within a cooldown period are excluded.
    """
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        # Source-level nudges
        source_rows = conn.execute(
            """
            WITH user_visible_sources AS (
              SELECT s.slug, s.name
              FROM sources s
              LEFT JOIN user_sources us
                ON us.source_slug = s.slug AND us.user_id = %(uid)s
              WHERE (s.owner_user_id IS NULL OR s.owner_user_id = %(uid)s)
                AND CASE WHEN s.owner_user_id IS NULL THEN COALESCE(us.enabled, TRUE)
                         ELSE s.enabled IS TRUE END
            ),
            source_totals AS (
              SELECT
                uvs.slug,
                uvs.name,
                COUNT(a.id) FILTER (
                  WHERE a.discovered_at::timestamptz >= NOW() - INTERVAL '30 days'
                ) AS articles_last_30_days,
                COUNT(uas.article_id) FILTER (
                  WHERE a.discovered_at::timestamptz >= NOW() - INTERVAL '30 days'
                    AND uas.state = 'skipped'
                ) AS skipped_count
              FROM user_visible_sources uvs
              LEFT JOIN articles a ON a.source_slug = uvs.slug
              LEFT JOIN user_article_state uas
                ON uas.article_id = a.id AND uas.user_id = %(uid)s
              GROUP BY uvs.slug, uvs.name
            )
            SELECT slug, name, articles_last_30_days, skipped_count
            FROM source_totals
            WHERE articles_last_30_days >= %(min_art)s
            ORDER BY
              CASE WHEN articles_last_30_days > 0
                   THEN skipped_count::float / articles_last_30_days ELSE 0 END DESC
            """,
            {
                "uid": user_id,
                "min_art": _LOW_SIGNAL_MIN_ARTICLES,
            },
        ).fetchall()

        # Topic-level nudges
        topic_rows = conn.execute(
            """
            WITH cat_totals AS (
              SELECT
                a.category,
                COUNT(a.id) FILTER (
                  WHERE a.discovered_at::timestamptz >= NOW() - INTERVAL '30 days'
                ) AS articles_last_30_days,
                COUNT(uas.article_id) FILTER (
                  WHERE a.discovered_at::timestamptz >= NOW() - INTERVAL '30 days'
                    AND uas.state = 'skipped'
                ) AS skipped_count
              FROM articles a
              LEFT JOIN user_article_state uas
                ON uas.article_id = a.id AND uas.user_id = %(uid)s
              WHERE a.category IS NOT NULL AND a.category <> ''
              GROUP BY a.category
            )
            SELECT category, articles_last_30_days, skipped_count
            FROM cat_totals
            WHERE articles_last_30_days >= %(min_art)s
            ORDER BY
              CASE WHEN articles_last_30_days > 0
                   THEN skipped_count::float / articles_last_30_days ELSE 0 END DESC
            """,
            {"uid": user_id, "min_art": _TOPIC_MIN_ARTICLES},
        ).fetchall()

        # Active dismissals (still within cooldown)
        dismissed_rows = conn.execute(
            """
            SELECT nudge_kind, nudge_target
            FROM user_nudge_dismissals
            WHERE user_id = %s AND cooldown_until > NOW()
            """,
            (user_id,),
        ).fetchall()

    dismissed: set[tuple[str, str]] = {
        (str(r["nudge_kind"]), str(r["nudge_target"])) for r in dismissed_rows
    }

    nudges: list[dict[str, Any]] = []

    for row in source_rows:
        source = row_to_dict(row)
        total = _as_int(source.get("articles_last_30_days"))
        skipped = _as_int(source.get("skipped_count"))
        skip_rate = round(skipped / total, 2) if total else 0.0
        if skip_rate <= _LOW_SIGNAL_SKIP_RATE:
            continue
        slug = str(source["slug"])
        if ("source", slug) in dismissed:
            continue
        name = str(source["name"])
        nudges.append(
            {
                "id": f"source:{slug}",
                "kind": "source",
                "title": f"Noisy source: {name}",
                "message": f"You've skipped {skip_rate:.0%} of recent articles from '{name}'.",
                "reason": "low_signal",
                "skip_rate": skip_rate,
                "articles_last_30_days": total,
                "action": "disable_source",
                "target": slug,
                "target_label": name,
            }
        )

    for row in topic_rows:
        topic = row_to_dict(row)
        total = _as_int(topic.get("articles_last_30_days"))
        skipped = _as_int(topic.get("skipped_count"))
        skip_rate = round(skipped / total, 2) if total else 0.0
        if skip_rate <= _TOPIC_SKIP_RATE:
            continue
        category = str(topic["category"])
        if ("topic", category) in dismissed:
            continue
        nudges.append(
            {
                "id": f"topic:{category}",
                "kind": "topic",
                "title": f"Noisy topic: {category.capitalize()}",
                "message": (
                    f"You've skipped {skip_rate:.0%} of recent '{category}' articles. "
                    "Reduce its weight in your feed?"
                ),
                "reason": "low_signal",
                "skip_rate": skip_rate,
                "articles_last_30_days": total,
                "action": "reduce_topic_weight",
                "target": category,
                "target_label": category.capitalize(),
            }
        )

    nudges.sort(key=lambda n: n["skip_rate"], reverse=True)
    return nudges[:max_results]


def apply_nudge(
    user_id: int,
    nudge_id: str,
    *,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Apply the action for *nudge_id* and record a permanent dismissal."""
    if ":" not in nudge_id:
        return {"applied": False, "error": "invalid nudge id"}

    kind, target = nudge_id.split(":", 1)
    init_db(db_path, database_url=database_url)

    if kind == "source":
        with connect(db_path, database_url=database_url) as conn:
            row = conn.execute(
                """
                SELECT slug, owner_user_id FROM sources
                WHERE slug = %s AND (owner_user_id IS NULL OR owner_user_id = %s)
                """,
                (target, user_id),
            ).fetchone()
            if row is None:
                return {"applied": False, "error": "source not found"}
            source = row_to_dict(row)
            if source.get("owner_user_id") is None:
                conn.execute(
                    """
                    INSERT INTO user_sources(user_id, source_slug, enabled)
                    VALUES (%s, %s, FALSE)
                    ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = FALSE
                    """,
                    (user_id, target),
                )
            else:
                conn.execute(
                    "UPDATE sources SET enabled = FALSE WHERE slug = %s AND owner_user_id = %s",
                    (target, user_id),
                )
            _record_dismissal(conn, user_id, kind, target, cooldown_days=365)
        return {"applied": True, "kind": kind, "target": target}

    if kind == "topic":
        from news_dashboard.recommendations import (
            get_recommendation_preferences,
            save_recommendation_preferences,
        )

        prefs = get_recommendation_preferences(user_id, db_path=db_path, database_url=database_url)
        current_weight = prefs.category_weights.get(target, 1.0)
        new_weight = max(0.0, round(current_weight - _TOPIC_WEIGHT_REDUCTION, 2))
        updated_weights = {**prefs.category_weights, target: new_weight}
        save_recommendation_preferences(
            user_id,
            category_weights=updated_weights,
            db_path=db_path,
            database_url=database_url,
        )
        with connect(db_path, database_url=database_url) as conn:
            _record_dismissal(conn, user_id, kind, target, cooldown_days=365)
        return {"applied": True, "kind": kind, "target": target, "new_weight": new_weight}

    return {"applied": False, "error": f"unknown nudge kind: {kind}"}


def dismiss_nudge(
    user_id: int,
    nudge_id: str,
    *,
    cooldown_days: int = _DEFAULT_COOLDOWN_DAYS,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Dismiss *nudge_id* without applying its action; suppresses for *cooldown_days*."""
    if ":" not in nudge_id:
        return {"dismissed": False, "error": "invalid nudge id"}
    kind, target = nudge_id.split(":", 1)
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        _record_dismissal(conn, user_id, kind, target, cooldown_days=cooldown_days)
    return {"dismissed": True, "kind": kind, "target": target, "cooldown_days": cooldown_days}


def _record_dismissal(
    conn: Any,
    user_id: int,
    kind: str,
    target: str,
    *,
    cooldown_days: int,
) -> None:
    conn.execute(
        """
        INSERT INTO user_nudge_dismissals(user_id, nudge_kind, nudge_target, cooldown_until)
        VALUES (%s, %s, %s, NOW() + (%s || ' days')::INTERVAL)
        ON CONFLICT(user_id, nudge_kind, nudge_target) DO UPDATE
          SET dismissed_at = NOW(),
              cooldown_until = NOW() + (%s || ' days')::INTERVAL
        """,
        (user_id, kind, target, cooldown_days, cooldown_days),
    )
