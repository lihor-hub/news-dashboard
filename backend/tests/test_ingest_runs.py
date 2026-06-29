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
