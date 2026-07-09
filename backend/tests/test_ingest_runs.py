from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import news_dashboard.ingest as ingest_module
from news_dashboard.db import connect
from news_dashboard.ingest import FeedFetchError, ingest_all
from news_dashboard.ingest_events import (
    IngestStreamEvent,
    format_sse_event,
    ingest_events,
    stream_ingest_events,
)
from news_dashboard.main import app
from news_dashboard.sources import SourceDefinition


def test_ingest_all_writes_run_rows_and_buffers_terminal_lines(
    tmp_path: Path, monkeypatch: Any
) -> None:
    db_path = tmp_path / "runs.db"
    source = SourceDefinition("test-feed", "Test Feed", "https://example.com/feed.xml", "python")
    ingest_events.reset_for_tests()
    monkeypatch.setattr(ingest_module, "DEFAULT_SOURCES", [source])

    def fake_parse_url(url: str) -> list[dict[str, object]]:
        assert url == source.url
        return [
            {
                "url": "https://example.com/article",
                "title": "Python release notes",
                "description": "A useful release summary.",
                "date": None,
            }
        ]

    monkeypatch.setattr(ingest_module, "_parse_feed_url", fake_parse_url)

    result = ingest_all(db_path)
    assert result.results == {"test-feed": 1}
    assert result.total_errors == 0

    with connect(db_path) as conn:
        run = conn.execute("SELECT * FROM ingest_runs").fetchone()
        sources = conn.execute("SELECT * FROM ingest_run_sources").fetchall()

    assert run["finished_at"] is not None
    assert run["duration_ms"] is not None
    assert run["total_new"] == 1
    assert run["total_errors"] == 0
    assert len(sources) == 1
    assert sources[0]["run_id"] == run["id"]
    assert sources[0]["source_name"] == "Test Feed"
    assert sources[0]["articles_found"] == 1
    assert sources[0]["articles_new"] == 1
    assert sources[0]["error_message"] is None

    terminal_lines = ingest_events.snapshot_last_completed()
    assert terminal_lines[0].startswith(f"Ingest run #{run['id']} started at ")
    assert any(line.startswith("✓ Test Feed — 1 new article") for line in terminal_lines)
    assert terminal_lines[-1].startswith("Summary — 1 new article")


def test_ingest_all_records_source_errors(tmp_path: Path, monkeypatch: Any) -> None:
    db_path = tmp_path / "errors.db"
    source = SourceDefinition("bad-feed", "Bad Feed", "https://example.com/bad.xml", "python")
    ingest_events.reset_for_tests()
    monkeypatch.setattr(ingest_module, "DEFAULT_SOURCES", [source])

    def fake_parse_url(_url: str) -> list[dict[str, object]]:
        msg = "connection timeout"
        raise FeedFetchError(msg)

    monkeypatch.setattr(ingest_module, "_parse_feed_url", fake_parse_url)

    result = ingest_all(db_path)
    assert result.results == {"bad-feed": -1}
    assert result.total_errors == 1
    assert result.failed_sources == ["bad-feed"]

    with connect(db_path) as conn:
        run = conn.execute("SELECT * FROM ingest_runs").fetchone()
        source_row = conn.execute("SELECT * FROM ingest_run_sources").fetchone()

    assert run["total_new"] == 0
    assert run["total_errors"] == 1
    assert source_row["source_name"] == "Bad Feed"
    assert source_row["articles_found"] == 0
    assert source_row["articles_new"] == 0
    assert source_row["error_message"] == "connection timeout"
    assert any(
        line == "✗ Bad Feed — connection timeout"
        for line in ingest_events.snapshot_last_completed()
    )


def test_ingest_source_skips_entry_that_raises_and_keeps_the_rest(
    tmp_path: Path, monkeypatch: Any
) -> None:
    # A single entry that trips a DB error (e.g. a unique violation on
    # articles_url_key) must not abort the whole source: the other entries for
    # that source should still be committed, and the source should not report a
    # total failure.
    db_path = tmp_path / "resilient.db"
    source = SourceDefinition("mixed-feed", "Mixed Feed", "https://example.com/mixed.xml", "python")
    ingest_events.reset_for_tests()
    monkeypatch.setattr(ingest_module, "DEFAULT_SOURCES", [source])

    def fake_parse_url(_url: str) -> list[dict[str, object]]:
        return [
            {
                "url": "https://example.com/good",
                "title": "Good release notes",
                "description": "A useful release summary.",
                "date": None,
            },
            {
                "url": "https://example.com/bad",
                "title": "Bad release notes",
                "description": "Another useful release summary.",
                "date": None,
            },
        ]

    monkeypatch.setattr(ingest_module, "_parse_feed_url", fake_parse_url)

    # Reproduce a per-entry DB failure that poisons the transaction the way a
    # real duplicate-key violation would: for the "bad" entry, insert the same
    # url twice so the second insert raises a unique violation.
    real_find_canonical = ingest_module._find_canonical

    def flaky_find_canonical(conn: Any, url: str, title: str, owner: Any = None) -> Any:
        if "bad" in url:
            collide = "https://example.com/collide"
            for _ in range(2):
                conn.execute(
                    "INSERT INTO articles(url, canonical_url, title, source_slug,"
                    " source_name, category, kind)"
                    " VALUES (%s, %s, 'dup', %s, %s, 'python', 'rss_feed')",
                    (collide, collide, source.slug, source.name),
                )
        return real_find_canonical(conn, url, title, owner)

    monkeypatch.setattr(ingest_module, "_find_canonical", flaky_find_canonical)

    result = ingest_all(db_path)

    # The good entry survives and the source is not reported as a total failure.
    assert result.total_errors == 0
    assert result.results == {"mixed-feed": 1}

    with connect(db_path) as conn:
        urls = {row["url"] for row in conn.execute("SELECT url FROM articles").fetchall()}
        source_row = conn.execute("SELECT * FROM ingest_run_sources").fetchone()

    assert "https://example.com/good" in urls
    # The failing entry's rolled-back insert must leave no trace.
    assert "https://example.com/collide" not in urls
    assert source_row["error_message"] is None
    assert source_row["articles_new"] == 1


def test_ingest_stream_route_is_registered() -> None:
    # url_path_for raises NoMatchFound (KeyError) if the route isn't registered.
    # Using url_path_for is robust across FastAPI versions (0.137+ stores included
    # routers as _IncludedRouter objects rather than flattening into app.routes).
    assert str(app.url_path_for("ingest_stream")) == "/api/ingest/stream"


def test_ingest_stream_replays_last_completed_run() -> None:
    ingest_events.reset_for_tests()
    ingest_events.start_run(7, "Ingest run #7 started at 2026-06-06T12:00:00+00:00")
    ingest_events.append_line("✓ Test Feed — 2 new articles (0.1s)")
    ingest_events.complete_run("Summary — 2 new articles (0.1s)")

    stream = stream_ingest_events()
    try:
        chunks = [next(stream) for _ in range(4)]
    finally:
        if isinstance(stream, Generator):
            stream.close()

    assert chunks[0] == format_sse_event(IngestStreamEvent("reset"))
    assert "data: Ingest run #7 started at 2026-06-06T12:00:00+00:00" in chunks[1]
    assert "data: ✓ Test Feed — 2 new articles (0.1s)" in chunks[2]
    assert "data: Summary — 2 new articles (0.1s)" in chunks[3]
