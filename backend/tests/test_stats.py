from __future__ import annotations

from pathlib import Path

from news_dashboard.db import connect, init_db
from news_dashboard.stats import articles_over_time, sources_volume, stats_overview


def _insert_run(
    db_path: Path,
    run_id: int,
    started_at: str,
    total_new: int,
    total_errors: int,
    duration_ms: int,
    sources: list[tuple[str, int, int, str | None]],
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ingest_runs(
              id, started_at, finished_at, duration_ms, total_new, total_errors
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, started_at, started_at, duration_ms, total_new, total_errors),
        )
        for source_name, found, new, error in sources:
            conn.execute(
                """
                INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, source_name, found, new, error),
            )


def test_overview_aggregates_run_and_source_stats(tmp_path: Path) -> None:
    db_path = tmp_path / "stats.db"
    init_db(db_path)
    _insert_run(
        db_path,
        1,
        "2026-06-01T10:00:00+00:00",
        7,
        1,
        1000,
        [
            ("Python Insider", 10, 5, None),
            ("Docker Blog", 4, 2, "timeout"),
        ],
    )
    _insert_run(
        db_path,
        2,
        "2026-06-02T10:00:00+00:00",
        3,
        0,
        3000,
        [
            ("Python Insider", 8, 3, None),
            ("Docker Blog", 2, 0, None),
        ],
    )

    assert stats_overview(
        "2026-06-01T00:00:00+00:00",
        "2026-06-03T00:00:00+00:00",
        db_path,
    ) == {
        "total_articles": 24,
        "total_new": 10,
        "total_errors": 1,
        "avg_duration_ms": 2000,
        "healthy_sources": 2,
        "erroring_sources": 0,
    }


def test_articles_over_time_includes_zero_activity_days(tmp_path: Path) -> None:
    db_path = tmp_path / "stats.db"
    init_db(db_path)
    _insert_run(db_path, 1, "2026-06-01T10:00:00+00:00", 4, 0, 1000, [])
    _insert_run(db_path, 2, "2026-06-03T10:00:00+00:00", 6, 0, 1000, [])

    assert articles_over_time(
        "2026-06-01T00:00:00+00:00",
        "2026-06-03T23:00:00+00:00",
        db_path,
    ) == [
        {"date": "2026-06-01", "new_articles": 4},
        {"date": "2026-06-02", "new_articles": 0},
        {"date": "2026-06-03", "new_articles": 6},
    ]


def test_articles_over_time_uses_hourly_buckets_for_one_day_ranges(tmp_path: Path) -> None:
    db_path = tmp_path / "stats.db"
    init_db(db_path)
    _insert_run(db_path, 1, "2026-06-01T10:30:00+00:00", 4, 0, 1000, [])
    _insert_run(db_path, 2, "2026-06-01T12:00:00+00:00", 6, 0, 1000, [])

    rows = articles_over_time(
        "2026-06-01T10:00:00+00:00",
        "2026-06-01T12:45:00+00:00",
        db_path,
    )

    assert rows == [
        {"date": "2026-06-01T10:00:00+00:00", "new_articles": 4},
        {"date": "2026-06-01T11:00:00+00:00", "new_articles": 0},
        {"date": "2026-06-01T12:00:00+00:00", "new_articles": 6},
    ]


def test_sources_volume_orders_by_total_new_descending(tmp_path: Path) -> None:
    db_path = tmp_path / "stats.db"
    init_db(db_path)
    _insert_run(
        db_path,
        1,
        "2026-06-01T10:00:00+00:00",
        10,
        0,
        1000,
        [
            ("Python Insider", 10, 3, None),
            ("Docker Blog", 10, 5, None),
        ],
    )
    _insert_run(
        db_path,
        2,
        "2026-06-02T10:00:00+00:00",
        6,
        0,
        1000,
        [
            ("Python Insider", 10, 6, None),
            ("Docker Blog", 10, 1, None),
        ],
    )

    assert sources_volume(
        "2026-06-01T00:00:00+00:00",
        "2026-06-03T00:00:00+00:00",
        db_path,
    ) == [
        {"source_name": "Python Insider", "total_new": 9},
        {"source_name": "Docker Blog", "total_new": 6},
    ]
