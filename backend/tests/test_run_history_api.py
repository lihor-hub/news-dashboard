from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from news_dashboard.db import connect, init_db
from news_dashboard.main import app

client = TestClient(app, raise_server_exceptions=True)


def _seed_db(db_path: Path) -> tuple[int, int]:
    init_db(db_path)
    with connect(db_path) as conn:
        r1 = conn.execute(
            """
            INSERT INTO ingest_runs(started_at, finished_at, duration_ms, total_new, total_errors)
            VALUES ('2026-06-06T10:00:00+00:00', '2026-06-06T10:00:02+00:00', 2000, 3, 1)
            RETURNING id
            """
        ).fetchone()["id"]
        r2 = conn.execute(
            """
            INSERT INTO ingest_runs(started_at, finished_at, duration_ms, total_new, total_errors)
            VALUES ('2026-06-06T11:00:00+00:00', '2026-06-06T11:00:01+00:00', 1000, 1, 0)
            RETURNING id
            """
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
            VALUES (%s, 'Python Insider', 5, 3, NULL)
            """,
            (r1,),
        )
        conn.execute(
            """
            INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
            VALUES (%s, 'Broken Feed', 0, 0, 'timeout')
            """,
            (r1,),
        )
        conn.execute(
            """
            INSERT INTO ingest_run_sources(
              run_id, source_name, articles_found, articles_new, error_message
            )
            VALUES (%s, 'Hacker News', 10, 1, NULL)
            """,
            (r2,),
        )
    return int(r1), int(r2)


def test_list_runs_returns_paginated_response(tmp_path: Path, monkeypatch: Any) -> None:
    db = tmp_path / "api_runs.db"
    import news_dashboard.db as db_mod
    import news_dashboard.run_history as rh_mod

    monkeypatch.setattr(db_mod, "DB_PATH", db)
    monkeypatch.setattr(rh_mod, "DB_PATH", db, raising=False)
    _seed_db(db)

    resp = client.get("/api/ingest/runs?page=1&per_page=10")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["has_more"] is False
    ids = [item["id"] for item in body["items"]]
    # reverse chronological: r2 before r1
    assert ids[0] > ids[1]


def test_list_runs_pagination(tmp_path: Path, monkeypatch: Any) -> None:
    db = tmp_path / "api_page.db"
    import news_dashboard.db as db_mod
    import news_dashboard.run_history as rh_mod

    monkeypatch.setattr(db_mod, "DB_PATH", db)
    monkeypatch.setattr(rh_mod, "DB_PATH", db, raising=False)
    _seed_db(db)

    resp = client.get("/api/ingest/runs?page=1&per_page=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["has_more"] is True
    assert len(body["items"]) == 1

    resp2 = client.get("/api/ingest/runs?page=2&per_page=1")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["has_more"] is False
    assert len(body2["items"]) == 1
    # Different run on page 2
    assert body2["items"][0]["id"] != body["items"][0]["id"]


def test_get_run_sources_returns_breakdown(tmp_path: Path, monkeypatch: Any) -> None:
    db = tmp_path / "api_sources.db"
    import news_dashboard.db as db_mod
    import news_dashboard.run_history as rh_mod

    monkeypatch.setattr(db_mod, "DB_PATH", db)
    monkeypatch.setattr(rh_mod, "DB_PATH", db, raising=False)
    r1, _ = _seed_db(db)

    resp = client.get(f"/api/ingest/runs/{r1}")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert len(body["items"]) == 2
    names = {s["source_name"] for s in body["items"]}
    assert names == {"Python Insider", "Broken Feed"}
    broken = next(s for s in body["items"] if s["source_name"] == "Broken Feed")
    assert broken["error_message"] == "timeout"
    python_insider = next(s for s in body["items"] if s["source_name"] == "Python Insider")
    assert python_insider["duplicates"] == 2  # 5 found - 3 new


def test_get_run_sources_404_for_unknown_id(tmp_path: Path, monkeypatch: Any) -> None:
    db = tmp_path / "api_404.db"
    import news_dashboard.db as db_mod
    import news_dashboard.run_history as rh_mod

    monkeypatch.setattr(db_mod, "DB_PATH", db)
    monkeypatch.setattr(rh_mod, "DB_PATH", db, raising=False)
    init_db(db)

    resp = client.get("/api/ingest/runs/9999")
    assert resp.status_code == 404


def test_list_runs_empty_state(tmp_path: Path, monkeypatch: Any) -> None:
    db = tmp_path / "api_empty.db"
    import news_dashboard.db as db_mod
    import news_dashboard.run_history as rh_mod

    monkeypatch.setattr(db_mod, "DB_PATH", db)
    monkeypatch.setattr(rh_mod, "DB_PATH", db, raising=False)
    init_db(db)

    resp = client.get("/api/ingest/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["has_more"] is False
