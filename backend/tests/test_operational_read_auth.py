"""Tests that GET /api/ingest/stream and GET /api/scheduler/status are admin-only."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from news_dashboard.main import app

_ADMIN_USER = {"id": 1, "username": "adminuser", "email": None, "is_admin": True}
_REGULAR_USER = {"id": 2, "username": "regularuser", "email": None, "is_admin": False}


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _deny_admin() -> None:
    raise HTTPException(status_code=403, detail="Admin access required")


# ── /api/ingest/stream ────────────────────────────────────────────────────────


def test_ingest_stream_requires_admin(client: TestClient) -> None:
    from news_dashboard.auth import require_admin, require_auth

    app.dependency_overrides[require_auth] = lambda: _REGULAR_USER
    app.dependency_overrides[require_admin] = _deny_admin
    try:
        resp = client.get("/api/ingest/stream")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_ingest_stream_succeeds_for_admin(client: TestClient) -> None:
    from news_dashboard.auth import require_admin, require_auth

    app.dependency_overrides[require_auth] = lambda: _ADMIN_USER
    app.dependency_overrides[require_admin] = lambda: _ADMIN_USER

    def _fake_stream() -> Generator[bytes]:
        yield b"data: {}\n\n"

    try:
        with patch("news_dashboard.main.stream_ingest_events", return_value=_fake_stream()):
            resp = client.get("/api/ingest/stream")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


# ── /api/scheduler/status ─────────────────────────────────────────────────────


def test_scheduler_status_requires_admin(client: TestClient) -> None:
    from news_dashboard.auth import require_admin, require_auth

    app.dependency_overrides[require_auth] = lambda: _REGULAR_USER
    app.dependency_overrides[require_admin] = _deny_admin
    try:
        resp = client.get("/api/scheduler/status")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_scheduler_status_succeeds_for_admin(client: TestClient) -> None:
    from news_dashboard.auth import require_admin, require_auth

    app.dependency_overrides[require_auth] = lambda: _ADMIN_USER
    app.dependency_overrides[require_admin] = lambda: _ADMIN_USER
    try:
        with (
            patch("news_dashboard.main.is_ingest_interval_enabled", return_value=True),
            patch("news_dashboard.main.get_next_ingest_at", return_value=None),
            patch("news_dashboard.main.is_paused", return_value=False),
            patch("news_dashboard.main.get_interval_minutes", return_value=60),
        ):
            resp = client.get("/api/scheduler/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "interval_minutes" in body
        assert "paused" in body
    finally:
        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)
