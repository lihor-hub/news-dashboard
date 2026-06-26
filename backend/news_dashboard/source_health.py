from __future__ import annotations

from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db, row_to_dict


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


def list_source_health(db_path: Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        source_rows = conn.execute(
            "SELECT * FROM sources ORDER BY category, priority DESC, name"
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
