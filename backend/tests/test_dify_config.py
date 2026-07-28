"""Tests for the optional public Dify chat configuration."""

from __future__ import annotations

import pytest

from news_dashboard.dify import public_dify_config

_DIFY_ENV = (
    "DIFY_CHAT_ENABLED",
    "DIFY_CHAT_BASE_URL",
    "DIFY_CHAT_APP_TOKEN",
    "DIFY_CHAT_TITLE",
)

_DISABLED_CONFIG: dict[str, object] = {
    "enabled": False,
    "base_url": None,
    "app_token": None,
    "title": "News Assistant",
}


@pytest.fixture(autouse=True)
def clear_dify_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep each case independent of the operator environment."""
    for name in _DIFY_ENV:
        monkeypatch.delenv(name, raising=False)


def test_public_dify_config_is_disabled_without_environment() -> None:
    assert public_dify_config() == _DISABLED_CONFIG


def test_public_dify_config_is_disabled_when_configuration_is_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIFY_CHAT_ENABLED", "true")
    monkeypatch.setenv("DIFY_CHAT_BASE_URL", "https://dify.example.test")

    assert public_dify_config() == _DISABLED_CONFIG


def test_public_dify_config_exposes_valid_https_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIFY_CHAT_ENABLED", "true")
    monkeypatch.setenv("DIFY_CHAT_BASE_URL", "https://dify.example.test")
    monkeypatch.setenv("DIFY_CHAT_APP_TOKEN", "public-embed-token")
    monkeypatch.setenv("DIFY_CHAT_TITLE", "Research assistant")

    assert public_dify_config() == {
        "enabled": True,
        "base_url": "https://dify.example.test",
        "app_token": "public-embed-token",
        "title": "Research assistant",
    }


def test_public_dify_config_removes_base_url_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIFY_CHAT_ENABLED", "true")
    monkeypatch.setenv("DIFY_CHAT_BASE_URL", "https://dify.example.test/")
    monkeypatch.setenv("DIFY_CHAT_APP_TOKEN", "public-embed-token")

    assert public_dify_config()["base_url"] == "https://dify.example.test"


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_public_dify_config_allows_http_loopback_hosts(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    monkeypatch.setenv("DIFY_CHAT_ENABLED", "true")
    monkeypatch.setenv("DIFY_CHAT_BASE_URL", f"http://{host}:5001")
    monkeypatch.setenv("DIFY_CHAT_APP_TOKEN", "public-embed-token")

    assert public_dify_config()["enabled"] is True


@pytest.mark.parametrize("base_url", ["http://dify.example.test", "ftp://dify.example.test"])
def test_public_dify_config_rejects_non_loopback_or_unsafe_urls(
    monkeypatch: pytest.MonkeyPatch, base_url: str
) -> None:
    monkeypatch.setenv("DIFY_CHAT_ENABLED", "true")
    monkeypatch.setenv("DIFY_CHAT_BASE_URL", base_url)
    monkeypatch.setenv("DIFY_CHAT_APP_TOKEN", "public-embed-token")

    assert public_dify_config() == _DISABLED_CONFIG


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DIFY_CHAT_APP_TOKEN", "token\nwith-control"),
        ("DIFY_CHAT_TITLE", "title\x1fwith-control"),
        ("DIFY_CHAT_APP_TOKEN", "x" * 513),
        ("DIFY_CHAT_TITLE", "x" * 121),
        ("DIFY_CHAT_BASE_URL", "https://dify.example.test/" + "x" * 2_023),
    ],
)
def test_public_dify_config_rejects_control_characters_and_oversized_values(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("DIFY_CHAT_ENABLED", "true")
    monkeypatch.setenv("DIFY_CHAT_BASE_URL", "https://dify.example.test")
    monkeypatch.setenv("DIFY_CHAT_APP_TOKEN", "public-embed-token")
    monkeypatch.setenv("DIFY_CHAT_TITLE", "News Assistant")
    monkeypatch.setenv(name, value)

    assert public_dify_config() == _DISABLED_CONFIG
