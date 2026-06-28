"""Tests that POST /api/ingest is restricted to admin users."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from news_dashboard.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


_FAKE_ADMIN = {
    "id": 1,
    "username": "adminuser",
    "email": None,
    "is_admin": True,
}


def test_ingest_requires_admin(client: TestClient) -> None:
    from news_dashboard.auth import require_admin, require_auth

    def _non_admin_require_admin() -> None:
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[require_auth] = lambda: {
        "id": 2,
        "username": "regularuser",
        "email": None,
        "is_admin": False,
    }
    app.dependency_overrides[require_admin] = _non_admin_require_admin
    try:
        resp = client.post("/api/ingest")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_ingest_succeeds_for_admin(client: TestClient) -> None:
    with (
        patch("news_dashboard.main.ingest_all", return_value={"feed1": 3, "feed2": 0}),
        patch("news_dashboard.main.prefetch_article_bodies"),
    ):
        resp = client.post("/api/ingest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] == 3
