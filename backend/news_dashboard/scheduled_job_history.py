"""Persistence layer for non-ingest scheduled-job run outcomes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from news_dashboard.db import connect, init_db, row_to_dict


def save_job_run(
    *,
    job_name: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    message: str | None = None,
) -> None:
    duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO scheduled_job_runs
              (job_name, started_at, finished_at, duration_ms, status, message)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (job_name, started_at, finished_at, duration_ms, status, message),
        )


def list_latest_job_runs() -> list[dict[str, Any]]:
    """Return the most recent run for each distinct job_name."""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT ON (job_name)
              id, job_name, started_at, finished_at, duration_ms, status, message
            FROM scheduled_job_runs
            ORDER BY job_name, started_at DESC
            """,
        ).fetchall()
    result = []
    for row in rows:
        d = row_to_dict(row)
        started = d.get("started_at")
        finished = d.get("finished_at")
        if isinstance(started, datetime):
            d["started_at"] = started.astimezone(timezone.utc).isoformat()
        if isinstance(finished, datetime):
            d["finished_at"] = finished.astimezone(timezone.utc).isoformat()
        result.append(d)
    return result
