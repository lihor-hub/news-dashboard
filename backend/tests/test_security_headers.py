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


def test_unhandled_server_error_gets_security_headers_without_leaking_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.system import service

    exception_detail = "private exception detail"

    def raise_unhandled_error() -> dict[str, object]:
        raise RuntimeError(exception_detail)

    monkeypatch.setattr(service, "public_config", raise_unhandled_error)
    resp = TestClient(app, raise_server_exceptions=False).get("/api/config")

    assert resp.status_code == 500
    assert resp.text == "Internal Server Error"
    assert exception_detail not in resp.text
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    with pytest.raises(RuntimeError, match=exception_detail):
        TestClient(app, raise_server_exceptions=True).get("/api/config")


def test_csp_allows_required_github_blob_and_data_resources() -> None:
    from news_dashboard.security_headers import content_security_policy

    policy = content_security_policy()

    assert _directive(policy, "connect-src") == "connect-src 'self' https://api.github.com"
    assert _directive(policy, "img-src") == "img-src 'self' data: blob:"
    assert _directive(policy, "media-src") == "media-src 'self' data: blob:"
    assert _directive(policy, "worker-src") == "worker-src 'self' blob:"
    assert _directive(policy, "style-src") == "style-src 'self' 'unsafe-inline'"
    assert _directive(policy, "manifest-src") == "manifest-src 'self'"


@pytest.mark.parametrize(
    ("dsn", "origin"),
    [
        ("https://public-key@o0.ingest.sentry.io/42", "https://o0.ingest.sentry.io"),
        (
            "http://public@glitchtip.example.test:8080/sentry/7",
            "http://glitchtip.example.test:8080",
        ),
    ],
)
def test_csp_allows_only_normalized_frontend_error_tracking_origin(
    monkeypatch: pytest.MonkeyPatch, dsn: str, origin: str
) -> None:
    from news_dashboard.security_headers import content_security_policy

    monkeypatch.setenv("SENTRY_DSN_FRONTEND", dsn)

    connect_src = _directive(content_security_policy(), "connect-src")

    assert connect_src == f"connect-src 'self' https://api.github.com {origin}"
    assert "public-key" not in connect_src
    assert "/sentry/7" not in connect_src


@pytest.mark.parametrize(
    "dsn",
    [
        "javascript://public@errors.example.test/1",
        "https://errors.example.test/1",
        "https://public@errors example.test/1",
        "https://public@errors.example.test/1?connect-src=https://evil.test",
        "https://public@errors.example.test/1 connect-src https://evil.test",
    ],
)
def test_csp_rejects_unsafe_frontend_error_tracking_dsn(
    monkeypatch: pytest.MonkeyPatch, dsn: str
) -> None:
    from news_dashboard.security_headers import content_security_policy

    monkeypatch.setenv("SENTRY_DSN_FRONTEND", dsn)

    assert _directive(content_security_policy(), "connect-src") == (
        "connect-src 'self' https://api.github.com"
    )


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


def test_enabled_swagger_docs_get_only_the_required_docs_csp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLE_API_DOCS", "true")

    resp = _client().get("/docs")
    policy = resp.headers["Content-Security-Policy"]

    assert resp.status_code == 200
    assert 'src="https://cdn.jsdelivr.net/' in resp.text
    assert 'href="https://cdn.jsdelivr.net/' in resp.text
    assert 'href="https://fastapi.tiangolo.com/' in resp.text
    assert _directive(policy, "script-src") == (
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'"
    )
    assert _directive(policy, "style-src") == (
        "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'"
    )
    assert _directive(policy, "img-src") == (
        "img-src 'self' data: blob: https://fastapi.tiangolo.com"
    )


def test_enabled_redoc_gets_only_the_required_docs_csp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLE_API_DOCS", "true")

    resp = _client().get("/redoc")
    policy = resp.headers["Content-Security-Policy"]

    assert resp.status_code == 200
    assert 'src="https://cdn.jsdelivr.net/' in resp.text
    assert 'href="https://fonts.googleapis.com/' in resp.text
    assert 'href="https://fastapi.tiangolo.com/' in resp.text
    assert _directive(policy, "script-src") == "script-src 'self' https://cdn.jsdelivr.net"
    assert _directive(policy, "style-src") == (
        "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'"
    )
    assert _directive(policy, "font-src") == "font-src 'self' data: https://fonts.gstatic.com"
    assert _directive(policy, "img-src") == (
        "img-src 'self' data: blob: https://fastapi.tiangolo.com"
    )


@pytest.mark.parametrize("path", ["/openapi.json", "/docs/", "/redoc/"])
def test_docs_exception_does_not_escape_exact_interactive_docs_paths(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.setenv("ENABLE_API_DOCS", "true")

    resp = _client().get(path)
    policy = resp.headers["Content-Security-Policy"]

    assert "https://cdn.jsdelivr.net" not in policy
    assert "https://fonts.googleapis.com" not in policy
    assert "'unsafe-inline'" not in _directive(policy, "script-src")


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_disabled_docs_get_not_found_with_strict_default_csp(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.delenv("ENABLE_API_DOCS", raising=False)

    resp = _client().get(path)
    policy = resp.headers["Content-Security-Policy"]

    assert resp.status_code == 404
    assert "https://cdn.jsdelivr.net" not in policy
    assert "'unsafe-inline'" not in _directive(policy, "script-src")
