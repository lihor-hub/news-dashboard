from __future__ import annotations

from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db, row_to_dict

LOW_SIGNAL_MIN_ARTICLES = 50
LOW_SIGNAL_SKIP_RATE = 0.9


def _clean_error(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    if "Traceback" in text:
        candidates = [
            line
            for line in lines
            if not line.startswith("Traceback")
            and not line.startswith("File ")
            and not line.startswith("raise ")
            and not line.startswith("^")
        ]
        text = candidates[-1] if candidates else lines[-1]
    else:
        text = lines[0]
    return text[:180] + ("..." if len(text) > 180 else "")


def _source_key(value: Any) -> str:
    return str(value or "").strip().lower()


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


def list_source_health(
    db_path: Path | str | None = None,
    *,
    user_id: int | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        source_rows = conn.execute(
            """
            SELECT * FROM sources
            WHERE (owner_user_id IS NULL
               OR (%s::integer IS NULL OR owner_user_id = %s))
              AND deleted_at IS NULL
            ORDER BY category, priority DESC, name
            """,
            (user_id, user_id),
        ).fetchall()
        run_rows = conn.execute(
            """
            WITH ordered AS (
              SELECT
                source_name,
                articles_new,
                error_message,
                ROW_NUMBER() OVER source_order AS row_number,
                COUNT(*) FILTER (
                  WHERE error_message IS NULL OR error_message = ''
                ) OVER (
                  PARTITION BY source_name
                  ORDER BY run_id DESC, id DESC
                  ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ) AS successes_before
              FROM ingest_run_sources
              WINDOW source_order AS (
                PARTITION BY source_name ORDER BY run_id DESC, id DESC
              )
            )
            SELECT source_name, articles_new, error_message
            FROM ordered
            WHERE row_number = 1 OR COALESCE(successes_before, 0) = 0
            ORDER BY source_name, row_number
            """
        ).fetchall()

    health_by_slug: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}

    for row in source_rows:
        source = row_to_dict(row)
        slug = str(source["slug"])
        last_error = _clean_error(source.get("last_error"))
        item = {
            "slug": slug,
            "name": source["name"],
            "category": source["category"],
            "enabled": source["enabled"],
            "last_checked_at": source.get("last_checked_at"),
            "last_error": last_error,
            "error_streak": 0,
            "articles_last_run": _as_int(source.get("last_inserted_count")),
            "status": "ERROR" if last_error else "OK",
        }
        health_by_slug[slug] = item
        aliases[_source_key(source.get("slug"))] = slug
        aliases[_source_key(source.get("name"))] = slug

    latest_seen: set[str] = set()
    streak_closed: set[str] = set()

    for row in run_rows:
        run = row_to_dict(row)
        run_slug = aliases.get(_source_key(run.get("source_name")))
        if not run_slug:
            continue

        item = health_by_slug[run_slug]
        error = _clean_error(run.get("error_message"))
        if run_slug not in latest_seen:
            item["articles_last_run"] = _as_int(run.get("articles_new"))
            latest_seen.add(run_slug)

        if run_slug in streak_closed:
            continue

        if error:
            item["error_streak"] += 1
            if not item["last_error"]:
                item["last_error"] = error
        else:
            streak_closed.add(run_slug)

    for slug, item in health_by_slug.items():
        if slug in latest_seen:
            item["status"] = "ERROR" if item["error_streak"] > 0 else "OK"
        else:
            item["status"] = "ERROR" if item["last_error"] else "OK"

    return sorted(
        health_by_slug.values(),
        key=lambda item: (
            -_as_int(item["error_streak"]),
            0 if item["status"] == "ERROR" else 1,
            str(item["name"]).lower(),
        ),
    )


def generate_subscription_cleanup_suggestions(
    user_id: int,
    *,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    """Find noisy or stale sources the user may want to unsubscribe from."""
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            """
            WITH user_visible_sources AS (
              SELECT s.slug, s.name
              FROM sources s
              LEFT JOIN user_sources us
                ON us.source_slug = s.slug AND us.user_id = %s
              WHERE (s.owner_user_id IS NULL OR s.owner_user_id = %s)
                AND s.deleted_at IS NULL
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
                ) AS skipped_count,
                COUNT(uas.article_id) FILTER (
                  WHERE a.discovered_at::timestamptz >= NOW() - INTERVAL '30 days'
                    AND uas.state = 'done'
                ) AS done_count,
                COUNT(uas.article_id) FILTER (
                  WHERE a.discovered_at::timestamptz >= NOW() - INTERVAL '30 days'
                    AND uas.starred IS TRUE
                ) AS starred_count,
                COUNT(uas.article_id) FILTER (
                  WHERE a.discovered_at::timestamptz >= NOW() - INTERVAL '30 days'
                    AND uas.state = 'archived'
                ) AS archived_count,
                COUNT(a.id) AS lifetime_articles
              FROM user_visible_sources uvs
              LEFT JOIN articles a ON a.source_slug = uvs.slug
              LEFT JOIN user_article_state uas
                ON uas.article_id = a.id AND uas.user_id = %s
              GROUP BY uvs.slug, uvs.name
            )
            SELECT *
            FROM source_totals
            WHERE lifetime_articles > 0
            ORDER BY articles_last_30_days DESC, name ASC
            """,
            (user_id, user_id, user_id),
        ).fetchall()

    suggestions: list[dict[str, Any]] = []
    for row in rows:
        source = row_to_dict(row)
        total = _as_int(source.get("articles_last_30_days"))
        skipped = _as_int(source.get("skipped_count"))
        done = _as_int(source.get("done_count"))
        starred = _as_int(source.get("starred_count"))
        archived = _as_int(source.get("archived_count"))
        skip_rate = round(skipped / total, 2) if total else 0.0
        engagement_score = round((done + starred) / total, 2) if total else 0.0
        source_name = str(source["name"])

        reason: str | None = None
        message: str | None = None
        if total >= LOW_SIGNAL_MIN_ARTICLES and skip_rate > LOW_SIGNAL_SKIP_RATE:
            reason = "low_signal"
            message = (
                f"Unsubscribe from '{source_name}' ({skip_rate:.0%} skipped in the last 30 days)"
            )
        elif total == 0:
            reason = "stale"
            message = f"Unsubscribe from '{source_name}' (no articles in the last 30 days)"

        if reason is None or message is None:
            continue

        suggestions.append(
            {
                "source_slug": str(source["slug"]),
                "source_name": source_name,
                "action": "unsubscribe",
                "reason": reason,
                "message": message,
                "articles_last_30_days": total,
                "skipped_count": skipped,
                "done_count": done,
                "starred_count": starred,
                "archived_count": archived,
                "skip_rate": _as_float(skip_rate),
                "engagement_score": _as_float(engagement_score),
            }
        )

    return suggestions
