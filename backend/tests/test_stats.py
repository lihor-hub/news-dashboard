from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from news_dashboard.db import connect, init_db
from news_dashboard.stats import (
    article_counts,
    articles_over_time,
    category_mix,
    ingested_vs_handled,
    source_quality,
    sources_volume,
    stats_overview,
    triage_metrics,
)


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
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (run_id, started_at, started_at, duration_ms, total_new, total_errors),
        )
        for source_name, found, new, error in sources:
            conn.execute(
                """
                INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
                VALUES (%s, %s, %s, %s, %s)
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


def _insert_article(  # noqa: PLR0913
    db_path: Path,
    *,
    url: str,
    source_name: str,
    category: str = "Engineering",
    status: str = "new",
    discovered_at: str | None = None,
    skipped_at: str | None = None,
    saved_at: str | None = None,
    read_at: str | None = None,
    archived_at: str | None = None,
) -> None:
    if discovered_at is None:
        discovered_at = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        # Ensure the referenced source exists (FK constraint).
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind, priority, enabled)"
            " VALUES ('src-1', %s, 'https://example.com/src-1.xml', %s, 'rss_feed', 50, TRUE)"
            " ON CONFLICT(slug) DO UPDATE SET name = EXCLUDED.name",
            (source_name, category),
        )
        conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name, category, kind,
              published_at, summary, reason, importance_score, tags,
              status, discovered_at, skipped_at, saved_at, read_at, archived_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (url) DO NOTHING
            """,
            (
                url,
                url,
                "Test Article",
                "src-1",
                source_name,
                category,
                "article",
                discovered_at,
                "summary",
                "reason",
                5,
                "[]",
                status,
                discovered_at,
                skipped_at,
                saved_at,
                read_at,
                archived_at,
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
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=2)).isoformat()
    _insert_article(db_path, url="u1", source_name="S", status="new", discovered_at=recent)
    _insert_article(
        db_path,
        url="u2",
        source_name="S",
        status="skipped",
        discovered_at=recent,
        skipped_at=(now - timedelta(days=2, hours=-1)).isoformat(),
    )
    _insert_article(
        db_path,
        url="u3",
        source_name="S",
        status="saved",
        discovered_at=recent,
        saved_at=(now - timedelta(days=2, hours=-2)).isoformat(),
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


def test_source_quality_handle_rate_counts_done_at_from_user_article_state(
    tmp_path: Path,
) -> None:
    """handle_rate must count articles with done_at set in user_article_state."""
    db_path = tmp_path / "quality_hr.db"
    init_db(db_path)
    now_ts = datetime.now(timezone.utc).isoformat()

    # Seed a user for FK constraint
    with connect(db_path) as conn:
        user_row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES ('tester', 'x') RETURNING id"
        ).fetchone()
        assert user_row is not None
        user_id = int(user_row["id"])

    # Alpha has 4 articles; we'll mark 1 as done
    _insert_article(db_path, url="a1", source_name="Alpha", status="new")
    _insert_article(db_path, url="a2", source_name="Alpha", status="new")
    _insert_article(db_path, url="a3", source_name="Alpha", status="new")
    _insert_article(db_path, url="a4", source_name="Alpha", status="new")
    # Beta has 2 articles; we'll mark both as done
    _insert_article(db_path, url="b1", source_name="Beta", status="new")
    _insert_article(db_path, url="b2", source_name="Beta", status="new")

    with connect(db_path) as conn:
        a1_id = int(conn.execute("SELECT id FROM articles WHERE url = 'a1'").fetchone()["id"])
        b1_id = int(conn.execute("SELECT id FROM articles WHERE url = 'b1'").fetchone()["id"])
        b2_id = int(conn.execute("SELECT id FROM articles WHERE url = 'b2'").fetchone()["id"])

        for art_id in (a1_id, b1_id, b2_id):
            conn.execute(
                "INSERT INTO user_article_state(user_id, article_id, state, done_at, updated_at)"
                " VALUES (%s, %s, 'done', %s, %s)",
                (user_id, art_id, now_ts, now_ts),
            )

    result = source_quality(db_path)
    alpha = next(r for r in result if r["source_name"] == "Alpha")
    beta = next(r for r in result if r["source_name"] == "Beta")

    # Alpha: 1 of 4 done → 25.0%
    assert alpha["total"] == 4
    assert alpha["handle_rate"] == 25.0
    # Beta: 2 of 2 done → 100.0%
    assert beta["total"] == 2
    assert beta["handle_rate"] == 100.0


def test_ingested_vs_handled_returns_14_days(tmp_path: Path) -> None:
    db_path = tmp_path / "ivh.db"
    init_db(db_path)

    result = ingested_vs_handled(db_path)
    assert len(result) == 14
    for row in result:
        assert "day" in row
        assert "ingested" in row
        assert "handled" in row


def test_ingested_vs_handled_counts_user_article_state_done(tmp_path: Path) -> None:
    """Regression: handled count must read user_article_state.done_at, not articles.read_at.

    Before the fix, ingested_vs_handled queried articles.read_at / articles.saved_at
    which are never written by the current state machine.  Users marking articles
    as 'done' writes user_article_state.done_at — the stats query must read that
    table and column.
    """
    db_path = tmp_path / "ivh_regression.db"
    init_db(db_path)

    with connect(db_path) as conn:
        # Seed a user (required for FK in user_article_state)
        user_row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES ('tester', 'x') RETURNING id"
        ).fetchone()
        assert user_row is not None
        user_id = int(user_row["id"])

        # Seed a source
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind) "
            "VALUES ('s', 'S', 'https://example.com', 'tech', 'rss_feed') "
            "ON CONFLICT(slug) DO NOTHING"
        )

        # Seed an article discovered today
        now_ts = datetime.now(timezone.utc).isoformat()
        art_row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug, source_name,
                                 category, kind, summary, discovered_at)
            VALUES ('https://e.com/a1', 'https://e.com/a1', 'A1', 's', 'S',
                    'tech', 'rss_feed', 's', %s)
            RETURNING id
            """,
            (now_ts,),
        ).fetchone()
        assert art_row is not None
        article_id = int(art_row["id"])

        # Mark the article as "done" by inserting into user_article_state
        # (exactly what transition_article_state does when user_id is provided)
        conn.execute(
            """
            INSERT INTO user_article_state(user_id, article_id, state, done_at, updated_at)
            VALUES (%s, %s, 'done', %s, %s)
            """,
            (user_id, article_id, now_ts, now_ts),
        )

    result = ingested_vs_handled(db_path)
    today_row = result[-1]

    assert today_row["ingested"] == 1, "ingested count should include today's article"
    assert today_row["handled"] == 1, (
        "handled count must read user_article_state.done_at — "
        "was zero because old query read articles.read_at which is never written"
    )


def test_ingested_vs_handled_handled_zero_when_only_articles_read_at_set(
    tmp_path: Path,
) -> None:
    """Confirm the old articles.read_at column is NOT counted as handled.

    If only articles.read_at is set (legacy data, no user_article_state row),
    the chart should show 0 handled — that column is no longer used by the
    current state machine and counting it would distort today's stats.
    """
    db_path = tmp_path / "ivh_legacy.db"
    init_db(db_path)

    now_ts = datetime.now(timezone.utc).isoformat()
    # Insert article with read_at set in the articles table (old pattern),
    # but NO corresponding user_article_state row.
    _insert_article(
        db_path,
        url="legacy1",
        source_name="L",
        status="read",
        discovered_at=now_ts,
        read_at=now_ts,
    )

    result = ingested_vs_handled(db_path)
    today_row = result[-1]
    assert today_row["ingested"] == 1
    assert today_row["handled"] == 0, (
        "articles.read_at must not be counted; handled reads user_article_state only"
    )


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
