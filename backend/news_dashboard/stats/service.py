from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db, placeholders, row_to_dict
from news_dashboard.scheduler.retention import retention_preview
from news_dashboard.stats.models import DatasetRange


def dataset_stats(
    range_key: DatasetRange,
    database_url: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return dataset coverage, PostgreSQL storage, and ingestion growth."""
    current = now or datetime.now(timezone.utc)
    init_db(database_url)
    with connect(database_url) as conn:
        summary = row_to_dict(
            conn.execute(
                """
                SELECT COUNT(*) AS article_count,
                       MIN(discovered_at) AS oldest_discovered_at,
                       MAX(discovered_at) AS newest_discovered_at
                FROM articles
                """
            ).fetchone()
        )
        storage = row_to_dict(
            conn.execute(
                """
                SELECT pg_database_size(current_database()) AS database_bytes,
                       pg_relation_size('articles'::regclass) AS article_heap_bytes,
                       pg_table_size('articles'::regclass)
                         - pg_relation_size('articles'::regclass) AS article_auxiliary_bytes,
                       pg_indexes_size('articles'::regclass) AS article_index_bytes,
                       pg_total_relation_size('articles'::regclass) AS article_total_bytes,
                       COALESCE((
                         SELECT percentile_cont(0.5) WITHIN GROUP
                           (ORDER BY pg_column_size(article_row.*))
                         FROM articles AS article_row
                       ), 0)::BIGINT AS median_article_bytes
                """
            ).fetchone()
        )
        trend, granularity = _dataset_trend(conn, range_key, current)

    article_count = _int_value(summary["article_count"])
    oldest = summary["oldest_discovered_at"]
    newest = summary["newest_discovered_at"]
    coverage_days = 0
    if oldest is not None and newest is not None:
        coverage_days = (_coerce_datetime(newest).date() - _coerce_datetime(oldest).date()).days
    total_bytes = _int_value(storage["article_total_bytes"])
    return {
        "summary": {
            "article_count": article_count,
            "oldest_discovered_at": _isoformat_or_none(oldest),
            "newest_discovered_at": _isoformat_or_none(newest),
            "coverage_days": coverage_days,
        },
        "storage": {
            **{key: _int_value(value) for key, value in storage.items()},
            "amortized_article_bytes": round(total_bytes / article_count) if article_count else 0,
        },
        "trend": trend,
        "trend_granularity": granularity,
        "retention_preview": retention_preview(database_url=database_url, now=current).as_dict(),
    }


def _dataset_trend(
    conn: Any, range_key: DatasetRange, now: datetime
) -> tuple[list[dict[str, Any]], str]:
    if range_key is DatasetRange.ALL:
        rows = conn.execute(
            """
            WITH bounds AS (
              SELECT date_trunc('month', MIN(discovered_at)) AS first_bucket
              FROM articles
            ), buckets AS (
              SELECT generate_series(first_bucket, date_trunc('month', %s::timestamptz),
                                     interval '1 month') AS bucket
              FROM bounds WHERE first_bucket IS NOT NULL
            ), counts AS (
              SELECT date_trunc('month', discovered_at) AS bucket, COUNT(*) AS articles
              FROM articles GROUP BY 1
            )
            SELECT buckets.bucket, COALESCE(counts.articles, 0) AS articles
            FROM buckets LEFT JOIN counts USING (bucket) ORDER BY buckets.bucket
            """,
            (now,),
        ).fetchall()
        granularity = "month"
    elif range_key is DatasetRange.ONE_YEAR:
        rows = conn.execute(
            """
            WITH buckets AS (
              SELECT generate_series(date_trunc('week', %s::timestamptz) - interval '51 weeks',
                                     date_trunc('week', %s::timestamptz),
                                     interval '1 week') AS bucket
            ), counts AS (
              SELECT date_trunc('week', discovered_at) AS bucket, COUNT(*) AS articles
              FROM articles
              WHERE discovered_at >= date_trunc('week', %s::timestamptz) - interval '51 weeks'
              GROUP BY 1
            )
            SELECT buckets.bucket, COALESCE(counts.articles, 0) AS articles
            FROM buckets LEFT JOIN counts USING (bucket) ORDER BY buckets.bucket
            """,
            (now, now, now),
        ).fetchall()
        granularity = "week"
    else:
        days = 30 if range_key is DatasetRange.THIRTY_DAYS else 90
        rows = conn.execute(
            """
            WITH buckets AS (
              SELECT generate_series(%s::date - (%s - 1), %s::date, interval '1 day') AS bucket
            ), counts AS (
              SELECT date_trunc('day', discovered_at) AS bucket, COUNT(*) AS articles
              FROM articles WHERE discovered_at >= %s::date - (%s - 1) GROUP BY 1
            )
            SELECT buckets.bucket, COALESCE(counts.articles, 0) AS articles
            FROM buckets LEFT JOIN counts USING (bucket) ORDER BY buckets.bucket
            """,
            (now, days, now, now, days),
        ).fetchall()
        granularity = "day"
    return [
        {
            "bucket": _coerce_datetime(row["bucket"]).date().isoformat(),
            "articles": _int_value(row["articles"]),
        }
        for row in rows
    ], granularity


def _isoformat_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return _coerce_datetime(value).isoformat()


def parse_range(from_value: str, to_value: str) -> tuple[datetime, datetime]:
    start = _parse_datetime(from_value)
    end = _parse_datetime(to_value)
    if start > end:
        message = "'from' must be before or equal to 'to'"
        raise ValueError(message)
    return start, end


def stats_overview(
    from_value: str, to_value: str, db_path: Path | str | None = None
) -> dict[str, Any]:
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
    from_value: str, to_value: str, db_path: Path | str | None = None
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
    from_value: str, to_value: str, db_path: Path | str | None = None
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


def ingested_vs_handled(db_path: Path | str | None = None, days: int = 14) -> list[dict[str, Any]]:
    """Return per-day ingested and handled article counts for the last `days` days."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    init_db(db_path)
    with connect(db_path) as conn:
        ingested_rows = [
            row_to_dict(r)
            for r in conn.execute(
                "SELECT DATE(discovered_at) AS day, COUNT(*) AS n FROM articles "
                "WHERE discovered_at >= %s GROUP BY day",
                (since,),
            ).fetchall()
        ]
        # Read from user_article_state (per-user workflow table).  The old
        # query hit articles.read_at / articles.saved_at which are never
        # written by the current state machine; the new state model uses
        # user_article_state.done_at / skipped_at / archived_at instead.
        # COUNT(DISTINCT article_id) avoids double-counting articles handled
        # by more than one user on the same day.
        handled_rows = [
            row_to_dict(r)
            for r in conn.execute(
                """
                SELECT DATE(COALESCE(uas.done_at, uas.skipped_at, uas.archived_at)) AS day,
                       COUNT(DISTINCT uas.article_id) AS n
                FROM user_article_state uas
                JOIN articles a ON a.id = uas.article_id
                WHERE a.discovered_at >= %s
                  AND (uas.done_at IS NOT NULL
                       OR uas.skipped_at IS NOT NULL
                       OR uas.archived_at IS NOT NULL)
                GROUP BY day
                """,
                (since,),
            ).fetchall()
        ]

    ingested_by_day = {str(r["day"]): _int_value(r["n"]) for r in ingested_rows}
    handled_by_day = {str(r["day"]): _int_value(r["n"]) for r in handled_rows}

    today = datetime.now(timezone.utc).date()
    return [
        {
            "day": (today - timedelta(days=days - 1 - i)).isoformat(),
            "ingested": ingested_by_day.get((today - timedelta(days=days - 1 - i)).isoformat(), 0),
            "handled": handled_by_day.get((today - timedelta(days=days - 1 - i)).isoformat(), 0),
        }
        for i in range(days)
    ]


def article_counts(db_path: Path | str | None = None) -> dict[str, int]:
    """Return total article count per status across all time.

    Reads from user_article_state (the live state machine table) rather than
    the legacy articles.status column, which is never updated by the current
    workflow.  COUNT(DISTINCT a.id) avoids double-counting when multiple users
    have acted on the same article.
    """
    init_db(db_path)
    with connect(db_path) as conn:
        row = row_to_dict(
            conn.execute(
                """
                SELECT
                  COUNT(DISTINCT a.id)
                    FILTER (WHERE uas.article_id IS NULL
                               OR (uas.state IN ('today', 'later')
                                   AND NOT uas.starred))           AS new,
                  COUNT(DISTINCT a.id)
                    FILTER (WHERE uas.starred = TRUE)              AS saved,
                  COUNT(DISTINCT a.id)
                    FILTER (WHERE uas.state = 'done')              AS read,
                  COUNT(DISTINCT a.id)
                    FILTER (WHERE uas.state = 'skipped')           AS skipped,
                  COUNT(DISTINCT a.id)
                    FILTER (WHERE uas.state = 'archived')          AS archived
                FROM articles a
                LEFT JOIN user_article_state uas ON uas.article_id = a.id
                """
            ).fetchone()
        )
    return {
        "new": _int_value(row["new"]),
        "saved": _int_value(row["saved"]),
        "read": _int_value(row["read"]),
        "skipped": _int_value(row["skipped"]),
        "archived": _int_value(row["archived"]),
    }


def triage_metrics(db_path: Path | str | None = None) -> dict[str, Any]:
    """Return habit metrics for articles discovered in the last 7 days.

    All counts read from user_article_state rather than the legacy
    articles.status / articles.*_at columns, which are never written by the
    current state machine when a user_id is present.
    """
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    init_db(db_path)
    with connect(db_path) as conn:
        total = row_to_dict(
            conn.execute(
                "SELECT COUNT(*) AS n FROM articles WHERE discovered_at >= %s",
                (week_ago,),
            ).fetchone()
        )["n"]

        # handled = any explicit action: state transition OR starred
        handled = row_to_dict(
            conn.execute(
                """
                SELECT COUNT(DISTINCT a.id) AS n
                FROM articles a
                JOIN user_article_state uas ON uas.article_id = a.id
                WHERE a.discovered_at >= %s
                  AND (uas.state IN ('done', 'skipped', 'archived')
                       OR uas.starred = TRUE)
                """,
                (week_ago,),
            ).fetchone()
        )["n"]

        # saved = starred (bookmark) action in the current state model
        saved = row_to_dict(
            conn.execute(
                """
                SELECT COUNT(DISTINCT a.id) AS n
                FROM articles a
                JOIN user_article_state uas ON uas.article_id = a.id
                WHERE a.discovered_at >= %s AND uas.starred = TRUE
                """,
                (week_ago,),
            ).fetchone()
        )["n"]

        triage_rows = [
            row_to_dict(r)
            for r in conn.execute(
                """
                SELECT a.discovered_at,
                       COALESCE(uas.done_at, uas.skipped_at, uas.archived_at,
                                uas.starred_at) AS triaged_at
                FROM articles a
                JOIN user_article_state uas ON uas.article_id = a.id
                WHERE a.discovered_at >= %s
                  AND (uas.done_at IS NOT NULL
                       OR uas.skipped_at IS NOT NULL
                       OR uas.archived_at IS NOT NULL
                       OR uas.starred_at IS NOT NULL)
                """,
                (week_ago,),
            ).fetchall()
        ]

    hours: list[float] = []
    for row in triage_rows:
        try:
            t_discovered = _coerce_datetime(row["discovered_at"])
            t_triaged = _coerce_datetime(row["triaged_at"])
            diff_h = (t_triaged - t_discovered).total_seconds() / 3600
            if diff_h >= 0:
                hours.append(diff_h)
        except Exception:  # noqa: S110
            pass

    avg_triage_hours = round(sum(hours) / len(hours), 1) if hours else 0.0
    return {
        "articles_this_week": total,
        "handled_rate": round(handled / total * 100) if total else 0,
        "save_rate": round(saved / total * 100) if total else 0,
        "avg_triage_hours": avg_triage_hours,
    }


def source_quality(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Return per-source quality stats computed from the articles table."""
    init_db(db_path)
    with connect(db_path) as conn:
        rows = [
            row_to_dict(r)
            for r in conn.execute(
                """
                WITH handled AS (
                  SELECT a2.source_name,
                         COUNT(DISTINCT uas.article_id) AS handled
                  FROM user_article_state uas
                  JOIN articles a2 ON a2.id = uas.article_id
                  WHERE uas.done_at IS NOT NULL
                  GROUP BY a2.source_name
                )
                SELECT
                  a.source_name,
                  COUNT(*) AS total,
                  SUM(CASE WHEN a.status = 'skipped' THEN 1 ELSE 0 END) AS skipped,
                  SUM(CASE WHEN a.status = 'saved'   THEN 1 ELSE 0 END) AS saved,
                  COALESCE(h.handled, 0) AS handled
                FROM articles a
                LEFT JOIN handled h ON h.source_name = a.source_name
                GROUP BY a.source_name, h.handled
                ORDER BY total DESC, a.source_name
                """
            ).fetchall()
        ]
        error_rows = [
            row_to_dict(r)
            for r in conn.execute(
                """
                SELECT name AS source_name,
                       CASE WHEN last_error IS NOT NULL AND last_error != '' THEN 1 ELSE 0 END
                         AS has_error
                FROM sources
                """
            ).fetchall()
        ]
    error_map = {r["source_name"]: bool(r["has_error"]) for r in error_rows}
    result = []
    for row in rows:
        total = _int_value(row["total"])
        skipped = _int_value(row["skipped"])
        saved = _int_value(row["saved"])
        handled = _int_value(row["handled"])
        has_error = error_map.get(str(row["source_name"]), False)
        result.append(
            {
                "source_name": row["source_name"],
                "total": total,
                "skip_rate": round(skipped / total * 100) if total else 0,
                "save_rate": round(saved / total * 100) if total else 0,
                "handle_rate": round(handled / total * 100, 1) if total else 0.0,
                "error_rate": 100 if has_error else 0,
            }
        )
    return result


def category_mix(db_path: Path | str | None = None, days: int = 14) -> list[dict[str, Any]]:
    """Return per-day article counts broken down by category for the last `days` days."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    init_db(db_path)
    with connect(db_path) as conn:
        rows = [
            row_to_dict(r)
            for r in conn.execute(
                """
                SELECT DATE(discovered_at) AS day, category, COUNT(*) AS n
                FROM articles
                WHERE discovered_at >= %s
                GROUP BY day, category
                ORDER BY day ASC
                """,
                (since,),
            ).fetchall()
        ]

    by_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    categories: set[str] = set()
    for row in rows:
        day = str(row["day"])
        cat = str(row["category"])
        by_day[day][cat] += _int_value(row["n"])
        categories.add(cat)

    today = datetime.now(timezone.utc).date()
    result = []
    for i in range(days):
        day_str = (today - timedelta(days=days - 1 - i)).isoformat()
        entry: dict[str, Any] = {"day": day_str}
        for cat in sorted(categories):
            entry[cat] = by_day[day_str].get(cat, 0)
        result.append(entry)
    return result


def _load_stats_rows(
    start: datetime,
    end: datetime,
    db_path: Path | str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    init_db(db_path)
    with connect(db_path) as conn:
        run_rows = conn.execute(
            """
            SELECT id, started_at, finished_at, duration_ms, total_new, total_errors
            FROM ingest_runs
            WHERE started_at >= %s AND started_at <= %s
            ORDER BY started_at ASC, id ASC
            """,
            (_to_query_value(start), _to_query_value(end)),
        ).fetchall()
        runs = [row_to_dict(row) for row in run_rows]
        run_ids = [row["id"] for row in runs]
        if not run_ids:
            return [], []

        run_placeholders = placeholders(run_ids)
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
            WHERE ingest_run_sources.run_id IN ({run_placeholders})
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
