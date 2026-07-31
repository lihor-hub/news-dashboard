"""Tests for the optional Sentry/GlitchTip error tracking gate."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sentry_sdk.types import Event

from news_dashboard.error_tracking import (
    _scrub_pii,
    error_tracking_enabled,
    frontend_error_tracking_dsn,
    init_error_tracking,
)
from news_dashboard.main import app


def _client() -> TestClient:
    app.dependency_overrides.clear()
    return TestClient(app, follow_redirects=False)


@pytest.mark.smoke
def test_error_tracking_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert error_tracking_enabled() is False


@pytest.mark.smoke
def test_error_tracking_enabled_when_dsn_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_DSN", "https://example@o0.ingest.sentry.io/0")
    assert error_tracking_enabled() is True


@pytest.mark.smoke
def test_init_does_not_call_sentry_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    mock_sentry_sdk = MagicMock()
    with patch.dict("sys.modules", {"sentry_sdk": mock_sentry_sdk}):
        init_error_tracking()
    mock_sentry_sdk.init.assert_not_called()


@pytest.mark.smoke
def test_init_calls_sentry_with_privacy_safe_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    dsn = "https://example@o0.ingest.sentry.io/0"
    monkeypatch.setenv("SENTRY_DSN", dsn)
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
    monkeypatch.setenv("SENTRY_RELEASE", "news-dashboard@1.2.3")
    mock_sentry_sdk = MagicMock()
    with patch.dict("sys.modules", {"sentry_sdk": mock_sentry_sdk}):
        init_error_tracking()
    mock_sentry_sdk.init.assert_called_once()
    _, kwargs = mock_sentry_sdk.init.call_args
    assert kwargs["dsn"] == dsn
    assert kwargs["environment"] == "production"
    assert kwargs["release"] == "news-dashboard@1.2.3"
    assert kwargs["send_default_pii"] is False
    assert kwargs["before_send"] is _scrub_pii


@pytest.mark.smoke
def test_frontend_dsn_unset_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_DSN_FRONTEND", raising=False)
    assert frontend_error_tracking_dsn() is None


@pytest.mark.smoke
@pytest.mark.parametrize(
    "dsn",
    [
        "https://example@o0.ingest.sentry.io/1",
        "http://public@glitchtip.example.test:8080/sentry/2",
    ],
)
def test_frontend_dsn_returned_when_valid(monkeypatch: pytest.MonkeyPatch, dsn: str) -> None:
    monkeypatch.setenv("SENTRY_DSN_FRONTEND", dsn)
    assert frontend_error_tracking_dsn() == dsn


@pytest.mark.parametrize(
    "dsn",
    [
        "javascript://public@errors.example.test/1",
        "https://errors.example.test/1",
        "https://public@errors example.test/1",
        "https://public@errors.example.test/",
        "https://public@errors.example.test/1?query=not-allowed",
        "https://public@errors.example.test/1\nconnect-src https://evil.test",
        "https://public@errors.example.test/1\n",
        "\u0085https://public@errors.example.test/1",
    ],
)
def test_frontend_dsn_rejects_malformed_or_unsafe_values(
    monkeypatch: pytest.MonkeyPatch, dsn: str
) -> None:
    monkeypatch.setenv("SENTRY_DSN_FRONTEND", dsn)
    assert frontend_error_tracking_dsn() is None


@pytest.mark.smoke
def test_scrub_pii_strips_cookies_headers_and_user() -> None:
    event = {
        "request": {
            "cookies": {"nd_session": "secret"},
            "headers": {
                "Authorization": "Bearer x",
                "Cookie": "nd_session=secret",
                "Accept": "*/*",
            },
        },
        "user": {"email": "a@b.com"},
    }
    scrubbed = cast("dict[str, Any]", _scrub_pii(cast("Event", event), cast("Any", {})))
    assert scrubbed is not None
    assert "cookies" not in scrubbed["request"]
    assert "Authorization" not in scrubbed["request"]["headers"]
    assert "Cookie" not in scrubbed["request"]["headers"]
    assert scrubbed["request"]["headers"]["Accept"] == "*/*"
    assert "user" not in scrubbed


@pytest.mark.smoke
def test_public_config_omits_dsn_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_DSN_FRONTEND", raising=False)
    for name in (
        "DIFY_CHAT_ENABLED",
        "DIFY_CHAT_BASE_URL",
        "DIFY_CHAT_APP_TOKEN",
        "DIFY_CHAT_TITLE",
    ):
        monkeypatch.delenv(name, raising=False)
    resp = _client().get("/api/config")
    assert resp.status_code == 200
    assert resp.json() == {
        "sentry_dsn": None,
        "dify": {
            "enabled": False,
            "base_url": None,
            "app_token": None,
            "title": "News Assistant",
        },
    }


@pytest.mark.smoke
def test_public_config_returns_frontend_dsn_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_DSN_FRONTEND", "https://example@o0.ingest.sentry.io/2")
    for name in (
        "DIFY_CHAT_ENABLED",
        "DIFY_CHAT_BASE_URL",
        "DIFY_CHAT_APP_TOKEN",
        "DIFY_CHAT_TITLE",
    ):
        monkeypatch.delenv(name, raising=False)
    resp = _client().get("/api/config")
    assert resp.status_code == 200
    assert resp.json() == {
        "sentry_dsn": "https://example@o0.ingest.sentry.io/2",
        "dify": {
            "enabled": False,
            "base_url": None,
            "app_token": None,
            "title": "News Assistant",
        },
    }
