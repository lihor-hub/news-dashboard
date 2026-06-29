"""Tests for scheduled_job_history module and the /api/scheduler/job-runs endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from news_dashboard.db import connect, init_db
from news_dashboard.main import app
from news_dashboard.scheduled_job_history import list_latest_job_runs, save_job_run


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


# ── save_job_run ──────────────────────────────────────────────────────────────


def test_save_job_run_success(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)

    started = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 6, 1, 8, 0, 2, tzinfo=timezone.utc)
    save_job_run(
        job_name="digest",
        started_at=started,
        finished_at=finished,
        status="success",
        message=None,
    )

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT job_name, status, duration_ms, message FROM scheduled_job_runs"
        ).fetchone()
    assert row is not None
    assert row["job_name"] == "digest"
    assert row["status"] == "success"
    assert row["duration_ms"] == 2000
    assert row["message"] is None


def test_save_job_run_failure_records_message(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)

    started = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 6, 1, 9, 0, 5, tzinfo=timezone.utc)
    save_job_run(
        job_name="recommendations",
        started_at=started,
        finished_at=finished,
        status="failure",
        message="connection refused",
    )

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT status, message FROM scheduled_job_runs WHERE job_name = 'recommendations'"
        ).fetchone()
    assert row is not None
    assert row["status"] == "failure"
    assert row["message"] == "connection refused"


def test_save_job_run_skipped(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)

    started = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    save_job_run(
        job_name="digest",
        started_at=started,
        finished_at=finished,
        status="skipped",
        message="no DIGEST_TO configured",
    )

    with connect(database_url=pg_clean) as conn:
        row = conn.execute("SELECT status FROM scheduled_job_runs").fetchone()
    assert row is not None
    assert row["status"] == "skipped"


# ── list_latest_job_runs ──────────────────────────────────────────────────────


def test_list_latest_job_runs_returns_one_per_job(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)

    t1 = datetime(2026, 6, 1, 7, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 1, 7, 0, 1, tzinfo=timezone.utc)
    t3 = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    t4 = datetime(2026, 6, 1, 8, 0, 1, tzinfo=timezone.utc)

    save_job_run(job_name="digest", started_at=t1, finished_at=t2, status="success")
    # second digest run — this should be the one returned
    save_job_run(job_name="digest", started_at=t3, finished_at=t4, status="failure", message="oops")
    save_job_run(job_name="recommendations", started_at=t1, finished_at=t2, status="success")

    rows = list_latest_job_runs()
    by_job = {r["job_name"]: r for r in rows}

    assert "digest" in by_job
    assert by_job["digest"]["status"] == "failure"
    assert by_job["digest"]["message"] == "oops"
    assert "recommendations" in by_job
    assert len(rows) == 2


def test_list_latest_job_runs_empty(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    assert list_latest_job_runs() == []


# ── /api/scheduler/job-runs endpoint ─────────────────────────────────────────


def test_api_job_runs_returns_items(client: TestClient, pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)

    started = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 6, 1, 8, 0, 3, tzinfo=timezone.utc)
    save_job_run(job_name="digest", started_at=started, finished_at=finished, status="success")

    resp = client.get("/api/scheduler/job-runs")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["job_name"] == "digest"
    assert item["status"] == "success"
    assert item["duration_ms"] == 3000


def test_api_job_runs_empty(client: TestClient, pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)

    resp = client.get("/api/scheduler/job-runs")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


# ── _run_and_record wrapper ───────────────────────────────────────────────────


def test_run_and_record_persists_success(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)

    from news_dashboard.scheduler import _run_and_record

    _run_and_record("digest", lambda: ("success", "all good"))

    with connect(database_url=pg_clean) as conn:
        row = conn.execute("SELECT status, message FROM scheduled_job_runs").fetchone()
    assert row is not None
    assert row["status"] == "success"
    assert row["message"] == "all good"


def test_run_and_record_persists_failure(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)

    from news_dashboard.scheduler import _run_and_record

    def failing_fn() -> tuple[str, str | None]:
        msg = "something broke"
        raise RuntimeError(msg)

    _run_and_record("recommendations", failing_fn)

    with connect(database_url=pg_clean) as conn:
        row = conn.execute("SELECT status FROM scheduled_job_runs").fetchone()
    assert row is not None
    assert row["status"] == "failure"


def test_run_and_record_skips_none_result(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)

    from news_dashboard.scheduler import _run_and_record

    _run_and_record("per_user_briefings", lambda: None)

    with connect(database_url=pg_clean) as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM scheduled_job_runs").fetchone()
    assert count is not None
    assert int(count["n"]) == 0


# ── _run_digest wrapper ───────────────────────────────────────────────────────


def test_run_digest_returns_success() -> None:
    with patch("news_dashboard.digest.send_digest", return_value=True):
        from news_dashboard.scheduler import _run_digest

        status, msg = _run_digest()
    assert status == "success"
    assert msg is None


def test_run_digest_returns_skipped_when_nothing_sent() -> None:
    with patch("news_dashboard.digest.send_digest", return_value=False):
        from news_dashboard.scheduler import _run_digest

        status, msg = _run_digest()
    assert status == "skipped"
    assert msg is not None


def test_run_digest_returns_failure_on_exception() -> None:
    with patch("news_dashboard.digest.send_digest", side_effect=RuntimeError("smtp down")):
        from news_dashboard.scheduler import _run_digest

        status, msg = _run_digest()
    assert status == "failure"
    assert msg is not None
    assert "smtp down" in (msg or "")
