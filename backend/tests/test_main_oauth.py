"""Tests for the public OAuth / Keycloak endpoints and the version endpoint.

The OAuth/login/OTP routes live in the ``auth_routes`` feature-module package
(mounted on ``main``'s ``public_router``); the version endpoints stay in
main.py. Keycloak helpers are patched so no real identity provider is
contacted; the TestClient is built without auth overrides because every route
here is public.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from news_dashboard import main as main_module
from news_dashboard.main import app


def _client() -> TestClient:
    app.dependency_overrides.clear()
    # follow_redirects=False so we can assert on the 3xx responses themselves.
    return TestClient(app, follow_redirects=False)


# ── /auth/login ───────────────────────────────────────────────────────────────


def test_keycloak_login_redirects_to_local_login_when_disabled() -> None:
    with patch(
        "news_dashboard.auth_routes.router.keycloak_config",
        return_value=SimpleNamespace(enabled=False),
    ):
        resp = _client().get("/auth/login")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login"


def test_keycloak_login_redirects_to_provider_and_sets_state_cookie() -> None:
    with (
        patch(
            "news_dashboard.auth_routes.router.keycloak_config",
            return_value=SimpleNamespace(enabled=True),
        ),
        patch(
            "news_dashboard.auth_routes.router.keycloak_authorization_url",
            return_value="https://idp.example/auth?state=x",
        ),
    ):
        resp = _client().get("/auth/login")
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://idp.example/auth?state=x"
    assert "nd_oauth_state" in resp.cookies


# ── /auth/callback ────────────────────────────────────────────────────────────


def test_keycloak_callback_rejects_missing_state() -> None:
    resp = _client().get("/auth/callback?code=abc")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login?auth_error=oauth_state"


def test_keycloak_callback_rejects_mismatched_state() -> None:
    client = _client()
    client.cookies.set("nd_oauth_state", "expected")
    resp = client.get("/auth/callback?state=different&code=abc")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login?auth_error=oauth_state"


def test_keycloak_callback_rejects_missing_code() -> None:
    client = _client()
    client.cookies.set("nd_oauth_state", "match")
    resp = client.get("/auth/callback?state=match")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login?auth_error=oauth_code"


def test_keycloak_callback_redirects_on_provider_denial() -> None:
    resp = _client().get("/auth/callback?error=access_denied&state=match")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login?auth_error=oauth_denied"


def test_keycloak_callback_redirects_on_token_exchange_failure() -> None:
    client = _client()
    client.cookies.set("nd_oauth_state", "match")
    exchange_error = HTTPException(status_code=401, detail="Keycloak token exchange failed")
    with patch(
        "news_dashboard.auth_routes.router.exchange_keycloak_code",
        new=AsyncMock(side_effect=exchange_error),
    ):
        resp = client.get("/auth/callback?state=match&code=bad")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login?auth_error=oauth_exchange_failed"


def test_keycloak_callback_success_sets_session_and_redirects() -> None:
    client = _client()
    client.cookies.set("nd_oauth_state", "match")
    with (
        patch(
            "news_dashboard.auth_routes.router.exchange_keycloak_code",
            new=AsyncMock(return_value={"id": 7, "is_admin": False}),
        ),
        patch("news_dashboard.auth_routes.router.create_session_token", return_value="sess-token"),
    ):
        resp = client.get("/auth/callback?state=match&code=good")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/"
    assert resp.cookies.get("nd_session") == "sess-token"


def test_keycloak_callback_success_returns_to_next_path() -> None:
    client = _client()
    client.cookies.set("nd_oauth_state", "match")
    client.cookies.set("nd_oauth_next", "/articles/42")
    with (
        patch(
            "news_dashboard.auth_routes.router.exchange_keycloak_code",
            new=AsyncMock(return_value={"id": 7, "is_admin": False}),
        ),
        patch("news_dashboard.auth_routes.router.create_session_token", return_value="sess-token"),
    ):
        resp = client.get("/auth/callback?state=match&code=good")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/articles/42"


def test_keycloak_callback_ignores_unsafe_next_path() -> None:
    client = _client()
    client.cookies.set("nd_oauth_state", "match")
    client.cookies.set("nd_oauth_next", "https://evil.example/steal")
    with (
        patch(
            "news_dashboard.auth_routes.router.exchange_keycloak_code",
            new=AsyncMock(return_value={"id": 7, "is_admin": False}),
        ),
        patch("news_dashboard.auth_routes.router.create_session_token", return_value="sess-token"),
    ):
        resp = client.get("/auth/callback?state=match&code=good")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/"


def test_keycloak_login_sets_next_cookie_for_safe_relative_path() -> None:
    with (
        patch(
            "news_dashboard.auth_routes.router.keycloak_config",
            return_value=SimpleNamespace(enabled=True),
        ),
        patch(
            "news_dashboard.auth_routes.router.keycloak_authorization_url",
            return_value="https://idp.example/auth?state=x",
        ),
    ):
        resp = _client().get("/auth/login?next=/articles/42")
    assert "/articles/42" in (resp.cookies.get("nd_oauth_next") or "")


def test_keycloak_login_ignores_unsafe_next_path() -> None:
    with (
        patch(
            "news_dashboard.auth_routes.router.keycloak_config",
            return_value=SimpleNamespace(enabled=True),
        ),
        patch(
            "news_dashboard.auth_routes.router.keycloak_authorization_url",
            return_value="https://idp.example/auth?state=x",
        ),
    ):
        resp = _client().get("/auth/login?next=https://evil.example")
    assert "nd_oauth_next" not in resp.cookies


# ── /auth/logout ──────────────────────────────────────────────────────────────


def test_keycloak_logout_redirects_to_provider_logout() -> None:
    with patch(
        "news_dashboard.auth_routes.router.keycloak_logout_url",
        return_value="https://idp.example/logout",
    ):
        resp = _client().get("/auth/logout")
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://idp.example/logout"


# ── /api/auth/login conflict when Keycloak is enabled ─────────────────────────


def test_password_login_returns_409_when_keycloak_enabled() -> None:
    with patch(
        "news_dashboard.auth_routes.router.keycloak_config",
        return_value=SimpleNamespace(enabled=True),
    ):
        resp = _client().post("/api/auth/login", json={"username": "u", "password": "p"})
    assert resp.status_code == 409


# ── /api/auth/config ──────────────────────────────────────────────────────────


def test_auth_config_returns_metadata() -> None:
    with patch(
        "news_dashboard.auth_routes.router.keycloak_auth_metadata",
        return_value={"provider": "password"},
    ):
        resp = _client().get("/api/auth/config")
    assert resp.status_code == 200
    assert resp.json() == {"provider": "password"}


# ── /api/version ──────────────────────────────────────────────────────────────


def test_read_app_version_reads_version_file() -> None:
    with patch("news_dashboard.main._VERSION_FILE") as vf:
        vf.read_text.return_value = "9.9.9\n"
        assert main_module._read_app_version() == "9.9.9"


def test_read_app_version_falls_back_to_unknown_on_oserror() -> None:
    with patch("news_dashboard.main._VERSION_FILE") as vf:
        vf.read_text.side_effect = OSError("missing")
        assert main_module._read_app_version() == "unknown"


def test_version_endpoint_returns_the_running_app_version() -> None:
    resp = _client().get("/api/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": app.version}


def test_app_version_matches_version_endpoint_and_openapi_info() -> None:
    """The FastAPI app version, /api/version, and OpenAPI info.version must agree."""
    resp = _client().get("/api/version")
    assert resp.json()["version"] == app.version
    assert app.openapi()["info"]["version"] == app.version
