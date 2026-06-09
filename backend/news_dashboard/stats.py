from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import connect, init_db, row_to_dict


def parse_range(from_value: str, to_value: str) -> tuple[datetime, datetime]:
    start = _parse_datetime(from_value)
    end = _parse_datetime(to_value)
    if start > end:
        message = "'from' must be before or equal to 'to'"
        raise ValueError(message)
    return start, end


def stats_overview(from_value: str, to_value: str, db_path: Path | None = None) -> dict[str, Any]:
    start, end = parse_range(from_value, to_value)
    runs, source_rows = _load_stats_rows(start, end, db_path)

    total_articles = sum(_int_value(row.get("articles_found")) for row in source_rows)
    total_new = sum(_int_value(row.get("total_new")) for row in runs)
    if total_new == 0 and source_rows:
        total_new = sum(_int_value(row.get("articles_new")) for row in source_rows)
    total_errors = sum(_int_value(row.get("total_errors")) for row in runs)
    if total_errors == 0 and source_rows:
        total_errors = sum(1 for row in source_rows if _has_error(row.get("error_message")))

    durations = [
        _int_value(row.get("duration_ms")) for row in runs if row.get("duration_ms") is not None
    ]
    latest_by_source: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        name = str(row["source_name"])
        current = latest_by_source.get(name)
        if current is None or _row_sort_key(row) > _row_sort_key(current):
            latest_by_source[name] = row

    erroring_sources = sum(
        1 for row in latest_by_source.values() if _has_error(row.get("error_message"))
    )
    healthy_sources = sum(
        1 for row in latest_by_source.values() if not _has_error(row.get("error_message"))
    )

    return {
        "total_articles": total_articles,
        "total_new": total_new,
        "total_errors": total_errors,
        "avg_duration_ms": round(sum(durations) / len(durations)) if durations else 0,
        "healthy_sources": healthy_sources,
        "erroring_sources": erroring_sources,
    }


def articles_over_time(
    from_value: str, to_value: str, db_path: Path | None = None
) -> list[dict[str, Any]]:
    start, end = parse_range(from_value, to_value)
    runs, _ = _load_stats_rows(start, end, db_path)
    hourly = end - start <= timedelta(days=1)
    counts: dict[str, int] = defaultdict(int)

    for row in runs:
        started_at = _coerce_datetime(row["started_at"])
        if hourly:
            bucket = started_at.replace(minute=0, second=0, microsecond=0)
            key = bucket.isoformat()
        else:
            key = started_at.date().isoformat()
        counts[key] += _int_value(row.get("total_new"))

    return [
        {"date": bucket, "new_articles": counts[bucket]}
        for bucket in _bucket_keys(start, end, hourly)
    ]


def sources_volume(
    from_value: str, to_value: str, db_path: Path | None = None
) -> list[dict[str, Any]]:
    start, end = parse_range(from_value, to_value)
    _, source_rows = _load_stats_rows(start, end, db_path)
    totals: dict[str, int] = defaultdict(int)
    for row in source_rows:
        totals[str(row["source_name"])] += _int_value(row.get("articles_new"))
    return [
        {"source_name": source_name, "total_new": total_new}
        for source_name, total_new in sorted(
            totals.items(), key=lambda item: (-item[1], item[0].lower())
        )
    ]


def _load_stats_rows(
    start: datetime,
    end: datetime,
    db_path: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    init_db(db_path)
    with connect(db_path) as conn:
        run_rows = conn.execute(
            """
            SELECT id, started_at, finished_at, duration_ms, total_new, total_errors
            FROM ingest_runs
            WHERE started_at >= ? AND started_at <= ?
            ORDER BY started_at ASC, id ASC
            """,
            (_to_query_value(start), _to_query_value(end)),
        ).fetchall()
        runs = [row_to_dict(row) for row in run_rows]
        run_ids = [row["id"] for row in runs]
        if not run_ids:
            return [], []

        placeholders = ", ".join("?" for _ in run_ids)
        source_rows = conn.execute(
            f"""
            SELECT
              ingest_run_sources.id,
              ingest_run_sources.run_id,
              ingest_run_sources.source_name,
              ingest_run_sources.articles_found,
              ingest_run_sources.articles_new,
              ingest_run_sources.error_message,
              ingest_runs.started_at
            FROM ingest_run_sources
            JOIN ingest_runs ON ingest_runs.id = ingest_run_sources.run_id
            WHERE ingest_run_sources.run_id IN ({placeholders})
            ORDER BY ingest_runs.started_at ASC, ingest_run_sources.id ASC
            """,
            tuple(run_ids),
        ).fetchall()
    return runs, [row_to_dict(row) for row in source_rows]


def _bucket_keys(start: datetime, end: datetime, hourly: bool) -> list[str]:
    if hourly:
        cursor = start.replace(minute=0, second=0, microsecond=0)
        last = end.replace(minute=0, second=0, microsecond=0)
        step = timedelta(hours=1)
        keys: list[str] = []
        while cursor <= last:
            keys.append(cursor.isoformat())
            cursor += step
        return keys

    cursor_date = start.date()
    last_date = end.date()
    keys = []
    while cursor_date <= last_date:
        keys.append(cursor_date.isoformat())
        cursor_date += timedelta(days=1)
    return keys


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        message = f"Invalid ISO datetime: {value}"
        raise ValueError(message) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_datetime(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else _parse_datetime(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_query_value(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _int_value(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


def _has_error(value: Any) -> bool:
    return bool(str(value).strip()) if value is not None else False


def _row_sort_key(row: dict[str, Any]) -> tuple[datetime, int]:
    return (_coerce_datetime(row["started_at"]), _int_value(row.get("id")))
