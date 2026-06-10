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


from news_dashboard.stats import article_counts, category_mix, ingested_vs_handled, source_quality, triage_metrics


def _insert_article(
    db_path: Path,
    *,
    url: str,
    source_name: str,
    category: str = "Engineering",
    status: str = "new",
    discovered_at: str = "2026-06-05T10:00:00+00:00",
    skipped_at: str | None = None,
    saved_at: str | None = None,
    read_at: str | None = None,
    archived_at: str | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name, category, kind,
              published_at, summary, reason, importance_score, tags,
              status, discovered_at, skipped_at, saved_at, read_at, archived_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (url) DO NOTHING
            """,
            (
                url, url, "Test Article", "src-1", source_name, category, "article",
                discovered_at, "summary", "reason", 5, "[]",
                status, discovered_at, skipped_at, saved_at, read_at, archived_at,
            ),
        )


def test_article_counts_returns_status_counts(tmp_path: Path) -> None:
    db_path = tmp_path / "counts.db"
    init_db(db_path)
    _insert_article(db_path, url="u1", source_name="S", status="new")
    _insert_article(db_path, url="u2", source_name="S", status="new")
    _insert_article(db_path, url="u3", source_name="S", status="skipped")
    _insert_article(db_path, url="u4", source_name="S", status="saved")

    result = article_counts(db_path)
    assert result["new"] == 2
    assert result["skipped"] == 1
    assert result["saved"] == 1
    assert result["read"] == 0


def test_triage_metrics_computes_handled_and_save_rates(tmp_path: Path) -> None:
    db_path = tmp_path / "triage.db"
    init_db(db_path)
    recent = "2026-06-09T10:00:00+00:00"
    _insert_article(db_path, url="u1", source_name="S", status="new", discovered_at=recent)
    _insert_article(
        db_path, url="u2", source_name="S", status="skipped",
        discovered_at=recent, skipped_at="2026-06-09T11:00:00+00:00"
    )
    _insert_article(
        db_path, url="u3", source_name="S", status="saved",
        discovered_at=recent, saved_at="2026-06-09T12:00:00+00:00"
    )

    result = triage_metrics(db_path)
    assert result["articles_this_week"] == 3
    assert result["handled_rate"] == 67  # 2/3 = 66.6% -> 67
    assert result["save_rate"] == 33  # 1/3 = 33.3% -> 33
    assert result["avg_triage_hours"] > 0


def test_source_quality_aggregates_per_source(tmp_path: Path) -> None:
    db_path = tmp_path / "quality.db"
    init_db(db_path)
    _insert_article(db_path, url="u1", source_name="Alpha", status="new")
    _insert_article(db_path, url="u2", source_name="Alpha", status="skipped")
    _insert_article(db_path, url="u3", source_name="Alpha", status="saved")
    _insert_article(db_path, url="u4", source_name="Beta", status="skipped")

    result = source_quality(db_path)
    alpha = next(r for r in result if r["source_name"] == "Alpha")
    assert alpha["total"] == 3
    assert alpha["skip_rate"] == 33
    assert alpha["save_rate"] == 33


def test_ingested_vs_handled_returns_14_days(tmp_path: Path) -> None:
    db_path = tmp_path / "ivh.db"
    init_db(db_path)

    result = ingested_vs_handled(db_path)
    assert len(result) == 14
    for row in result:
        assert "day" in row
        assert "ingested" in row
        assert "handled" in row


def test_category_mix_returns_14_days_with_categories(tmp_path: Path) -> None:
    db_path = tmp_path / "catmix.db"
    init_db(db_path)
    _insert_article(db_path, url="u1", source_name="S", category="AI/LLM")
    _insert_article(db_path, url="u2", source_name="S", category="Python")

    result = category_mix(db_path)
    assert len(result) == 14
    today_row = result[-1]
    assert "day" in today_row
    assert "AI/LLM" in today_row or "Python" in today_row
