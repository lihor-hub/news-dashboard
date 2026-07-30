"""Tests for the baseline browser security headers middleware."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from news_dashboard.main import app


def _directive(policy: str, name: str) -> str:
    return next(part.strip() for part in policy.split(";") if part.strip().startswith(f"{name} "))


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
@pytest.mark.parametrize(
    ("path", "expected_status"),
    [("/api/live", 200), ("/api/does-not-exist", 404)],
)
def test_default_csp_is_applied_to_success_and_not_found_responses(
    path: str, expected_status: int
) -> None:
    resp = _client().get(path)
    policy = resp.headers["Content-Security-Policy"]

    assert resp.status_code == expected_status
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in policy
    assert "object-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "'unsafe-inline'" not in _directive(policy, "script-src")


def test_csp_allows_required_github_blob_and_data_resources() -> None:
    from news_dashboard.security_headers import content_security_policy

    policy = content_security_policy()

    assert _directive(policy, "connect-src") == "connect-src 'self' https://api.github.com"
    assert _directive(policy, "img-src") == "img-src 'self' data: blob:"
    assert _directive(policy, "media-src") == "media-src 'self' data: blob:"
    assert _directive(policy, "worker-src") == "worker-src 'self' blob:"
    assert _directive(policy, "style-src") == "style-src 'self' 'unsafe-inline'"
    assert _directive(policy, "manifest-src") == "manifest-src 'self'"


def test_csp_allows_only_normalized_dify_origin_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.security_headers import content_security_policy

    monkeypatch.setenv("DIFY_CHAT_ENABLED", "true")
    monkeypatch.setenv("DIFY_CHAT_BASE_URL", "https://CHAT.example.test:8443/path/")
    monkeypatch.setenv("DIFY_CHAT_APP_TOKEN", "public-embed-token")

    policy = content_security_policy()

    assert _directive(policy, "frame-src") == ("frame-src 'self' https://chat.example.test:8443")
    assert "/path" not in _directive(policy, "frame-src")
    assert "chat.example.test" not in _directive(policy, "connect-src")
    assert "chat.example.test" not in _directive(policy, "script-src")


@pytest.mark.parametrize(
    ("enabled", "base_url"),
    [
        ("false", "https://disabled.example.test/path"),
        ("true", "https://invalid.example.test/path?query=not-allowed"),
    ],
)
def test_csp_does_not_allow_disabled_or_invalid_dify_configuration(
    monkeypatch: pytest.MonkeyPatch, enabled: str, base_url: str
) -> None:
    from news_dashboard.security_headers import content_security_policy

    monkeypatch.setenv("DIFY_CHAT_ENABLED", enabled)
    monkeypatch.setenv("DIFY_CHAT_BASE_URL", base_url)
    monkeypatch.setenv("DIFY_CHAT_APP_TOKEN", "public-embed-token")

    assert _directive(content_security_policy(), "frame-src") == "frame-src 'self'"


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
        assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
    finally:
        monkeypatch.delenv("ENABLE_HSTS", raising=False)
        importlib.reload(security_headers_module)


@pytest.mark.smoke
def test_setdefault_does_not_override_existing_headers() -> None:
    from starlette.responses import Response

    from news_dashboard.security_headers import apply_security_headers

    response = Response(
        content="ok",
        headers={
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": "default-src 'none'",
        },
    )
    apply_security_headers(response)

    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_enabled_api_docs_are_served_with_the_strict_application_csp(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.setenv("ENABLE_API_DOCS", "true")

    resp = _client().get(path)

    assert resp.status_code == 200
    assert "'unsafe-inline'" not in _directive(
        resp.headers["Content-Security-Policy"], "script-src"
    )
