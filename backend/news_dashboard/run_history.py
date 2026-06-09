from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .db import connect, init_db, row_to_dict


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _datetime_from_value(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_ms(
    started_at: datetime | str | None,
    finished_at: datetime | str | None,
    duration_ms: int | None,
) -> int | None:
    if duration_ms is not None:
        return duration_ms
    start = _datetime_from_value(started_at)
    end = _datetime_from_value(finished_at)
    if not start or not end:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def _run_from_row(row: Any) -> dict[str, Any]:
    data = row_to_dict(row)
    data["duration_ms"] = _duration_ms(
        data.get("started_at"),
        data.get("finished_at"),
        data.get("duration_ms"),
    )
    data["started_at"] = _iso(data.get("started_at"))
    data["finished_at"] = _iso(data.get("finished_at"))
    data["sources_run"] = int(data.get("sources_run") or 0)
    data["total_new"] = int(data.get("total_new") or 0)
    data["total_errors"] = int(data.get("total_errors") or 0)
    return data


def list_ingest_runs(
    *,
    from_: datetime | str | None = None,
    to: datetime | str | None = None,
    page: int = 1,
    per_page: int = 20,
    db_path: Path | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    filters = ["finished_at IS NOT NULL"]
    params: list[Any] = []
    from_iso = _iso(from_)
    to_iso = _iso(to)
    if from_iso:
        filters.append("started_at >= ?")
        params.append(from_iso)
    if to_iso:
        filters.append("started_at <= ?")
        params.append(to_iso)
    where = " AND ".join(filters)
    offset = (page - 1) * per_page

    with connect(db_path) as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS count FROM ingest_runs WHERE {where}",
            tuple(params),
        ).fetchone()
        total = int(total_row["count"] if isinstance(total_row, dict) else total_row[0])
        rows = conn.execute(
            f"""
            SELECT
              r.id,
              r.started_at,
              r.finished_at,
              r.duration_ms,
              (SELECT COUNT(*) FROM ingest_run_sources s WHERE s.run_id = r.id) AS sources_run,
              COALESCE(
                r.total_new,
                (
                  SELECT COALESCE(SUM(COALESCE(s.articles_new, 0)), 0)
                  FROM ingest_run_sources s WHERE s.run_id = r.id
                ),
                0
              ) AS total_new,
              COALESCE(
                r.total_errors,
                (
                  SELECT COUNT(*)
                  FROM ingest_run_sources s
                  WHERE s.run_id = r.id
                    AND s.error_message IS NOT NULL
                    AND s.error_message != ''
                ),
                0
              ) AS total_errors
            FROM ingest_runs r
            WHERE {where}
            ORDER BY r.started_at DESC, r.id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, per_page, offset),
        ).fetchall()

    return {
        "items": [_run_from_row(row) for row in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
        "has_more": offset + len(rows) < total,
    }


def get_ingest_run_sources(
    run_id: int, *, db_path: Path | None = None
) -> list[dict[str, Any]] | None:
    init_db(db_path)
    with connect(db_path) as conn:
        exists = conn.execute("SELECT id FROM ingest_runs WHERE id=?", (run_id,)).fetchone()
        if not exists:
            return None
        rows = conn.execute(
            """
            SELECT
              id,
              run_id,
              source_name,
              COALESCE(articles_found, 0) AS articles_found,
              COALESCE(articles_new, 0) AS articles_new,
              error_message
            FROM ingest_run_sources
            WHERE run_id=?
            ORDER BY id ASC
            """,
            (run_id,),
        ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        item = row_to_dict(row)
        found = int(item.get("articles_found") or 0)
        new = int(item.get("articles_new") or 0)
        item["articles_found"] = found
        item["articles_new"] = new
        item["duplicates"] = max(0, found - new)
        items.append(item)
    return items
