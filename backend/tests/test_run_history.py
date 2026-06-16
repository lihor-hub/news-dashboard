from __future__ import annotations

from pathlib import Path

from news_dashboard.db import connect, init_db
from news_dashboard.run_history import get_ingest_run_sources, list_ingest_runs


def _insert_run(
    db_path: Path,
    *,
    started_at: str,
    finished_at: str | None,
    duration_ms: int | None = None,
    total_new: int | None = None,
    total_errors: int | None = None,
) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO ingest_runs(started_at, finished_at, duration_ms, total_new, total_errors)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (started_at, finished_at, duration_ms, total_new, total_errors),
        )
        row = cursor.fetchone()
        return int(row["id"])


def _insert_source(
    db_path: Path,
    *,
    run_id: int,
    source_name: str,
    articles_found: int,
    articles_new: int,
    error_message: str | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (run_id, source_name, articles_found, articles_new, error_message),
        )


def test_run_history_tables_are_created(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    init_db(db)

    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO ingest_runs(started_at, finished_at, duration_ms, total_new, total_errors)
            VALUES ('2026-06-06T10:00:00+00:00', '2026-06-06T10:00:02+00:00', 2000, 3, 0)
            """
        )
        row = conn.execute("SELECT COUNT(*) AS count FROM ingest_runs").fetchone()

    assert row["count"] == 1


def test_list_ingest_runs_is_completed_reverse_chronological_and_paginated(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    init_db(db)
    first = _insert_run(
        db,
        started_at="2026-06-06T10:00:00+00:00",
        finished_at="2026-06-06T10:00:03+00:00",
    )
    second = _insert_run(
        db,
        started_at="2026-06-06T11:00:00+00:00",
        finished_at="2026-06-06T11:00:01+00:00",
    )
    _insert_run(
        db,
        started_at="2026-06-06T12:00:00+00:00",
        finished_at=None,
    )
    _insert_source(db, run_id=first, source_name="Python Insider", articles_found=4, articles_new=3)
    _insert_source(
        db,
        run_id=first,
        source_name="Broken Feed",
        articles_found=0,
        articles_new=0,
        error_message="timeout",
    )
    _insert_source(db, run_id=second, source_name="Hacker News", articles_found=10, articles_new=2)

    page = list_ingest_runs(page=1, per_page=1, db_path=db)

    assert page["total"] == 2
    assert page["has_more"] is True
    assert [run["id"] for run in page["items"]] == [second]
    assert page["items"][0]["sources_run"] == 1
    assert page["items"][0]["total_new"] == 2
    assert page["items"][0]["total_errors"] == 0

    page_2 = list_ingest_runs(page=2, per_page=1, db_path=db)
    assert [run["id"] for run in page_2["items"]] == [first]
    assert page_2["items"][0]["duration_ms"] == 3000
    assert page_2["items"][0]["sources_run"] == 2
    assert page_2["items"][0]["total_new"] == 3
    assert page_2["items"][0]["total_errors"] == 1


def test_list_ingest_runs_filters_by_started_at_window(tmp_path: Path) -> None:
    db = tmp_path / "filtered.db"
    init_db(db)
    _insert_run(
        db,
        started_at="2026-06-06T09:00:00+00:00",
        finished_at="2026-06-06T09:00:01+00:00",
        total_new=1,
        total_errors=0,
    )
    expected = _insert_run(
        db,
        started_at="2026-06-06T10:00:00+00:00",
        finished_at="2026-06-06T10:00:01+00:00",
        total_new=2,
        total_errors=0,
    )

    page = list_ingest_runs(
        from_="2026-06-06T09:30:00+00:00",
        to="2026-06-06T10:30:00+00:00",
        db_path=db,
    )

    assert [run["id"] for run in page["items"]] == [expected]


def test_get_ingest_run_sources_includes_duplicate_counts(tmp_path: Path) -> None:
    db = tmp_path / "sources.db"
    init_db(db)
    run_id = _insert_run(
        db,
        started_at="2026-06-06T10:00:00+00:00",
        finished_at="2026-06-06T10:00:03+00:00",
    )
    _insert_source(
        db, run_id=run_id, source_name="Python Insider", articles_found=5, articles_new=2
    )
    _insert_source(
        db,
        run_id=run_id,
        source_name="Broken Feed",
        articles_found=0,
        articles_new=0,
        error_message="timeout",
    )

    sources = get_ingest_run_sources(run_id, db_path=db)

    assert sources is not None
    assert sources[0]["duplicates"] == 3
    assert sources[1]["error_message"] == "timeout"
    assert get_ingest_run_sources(999, db_path=db) is None
