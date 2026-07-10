"""Tests for /api/live and /api/ready health probe endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from news_dashboard.main import app


def _client() -> TestClient:
    app.dependency_overrides.clear()
    return TestClient(app, follow_redirects=False)


@pytest.mark.smoke
def test_live_returns_200_without_db() -> None:
    with patch("news_dashboard.system.service.connect") as mock_connect:
        resp = _client().get("/api/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    mock_connect.assert_not_called()


@pytest.mark.smoke
def test_ready_returns_200_when_db_ok() -> None:
    @contextmanager
    def fake_connect() -> Iterator[object]:
        class _Conn:
            def execute(self, sql: str) -> None:
                pass

        yield _Conn()

    with patch("news_dashboard.system.service.connect", fake_connect):
        resp = _client().get("/api/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.smoke
def test_ready_returns_503_when_db_unavailable() -> None:
    @contextmanager
    def broken_connect() -> Iterator[object]:
        class _BrokenConn:
            def execute(self, sql: str) -> None:  # noqa: ARG002
                msg = "connection refused"
                raise OSError(msg)

        yield _BrokenConn()

    with patch("news_dashboard.system.service.connect", broken_connect):
        resp = _client().get("/api/ready")
    assert resp.status_code == 503


def test_health_details_reports_graph_status() -> None:
    from news_dashboard.auth import require_admin, require_auth

    client = _client()
    app.dependency_overrides[require_auth] = lambda: {
        "id": 1,
        "username": "admin",
        "is_admin": True,
    }
    app.dependency_overrides[require_admin] = lambda: None
    with (
        patch("news_dashboard.stats.router.init_db"),
        patch("news_dashboard.stats.router.describe_database", return_value="postgresql://db"),
        patch("news_dashboard.stats.router.get_next_ingest_at", return_value=None),
        patch("news_dashboard.system.service.graph_status", return_value={"status": "disabled"}),
    ):
        resp = client.get("/api/health/details")
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(require_auth, None)

    assert resp.status_code == 200
    assert resp.json()["graph"] == {"status": "disabled"}
