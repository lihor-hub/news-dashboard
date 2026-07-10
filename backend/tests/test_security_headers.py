"""Tests for the baseline browser security headers middleware."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from news_dashboard.main import app


def _client() -> TestClient:
    app.dependency_overrides.clear()
    return TestClient(app, follow_redirects=False)


@pytest.mark.smoke
def test_public_route_gets_baseline_headers() -> None:
    resp = _client().get("/api/live")

    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert resp.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"


@pytest.mark.smoke
def test_404_response_still_gets_baseline_headers() -> None:
    resp = _client().get("/api/does-not-exist")

    assert resp.status_code == 404
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


@pytest.mark.smoke
def test_hsts_absent_by_default() -> None:
    resp = _client().get("/api/live")

    assert "Strict-Transport-Security" not in resp.headers


@pytest.mark.smoke
def test_hsts_present_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_HSTS", "true")
    import news_dashboard.security_headers as security_headers_module

    importlib.reload(security_headers_module)
    try:
        resp = _client().get("/api/live")
        assert resp.headers["Strict-Transport-Security"] == (
            "max-age=31536000; includeSubDomains; preload"
        )
    finally:
        monkeypatch.delenv("ENABLE_HSTS", raising=False)
        importlib.reload(security_headers_module)


@pytest.mark.smoke
def test_setdefault_does_not_override_existing_header() -> None:
    from starlette.responses import Response

    from news_dashboard.security_headers import apply_security_headers

    response = Response(content="ok", headers={"X-Frame-Options": "SAMEORIGIN"})
    apply_security_headers(response)

    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
