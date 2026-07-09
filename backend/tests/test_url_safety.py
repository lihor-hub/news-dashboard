from __future__ import annotations

import io
import socket
import urllib.request
from http.client import HTTPMessage

import pytest

from news_dashboard.url_safety import (
    UnsafeUrlError,
    _ValidatingRedirectHandler,
    validate_server_fetch_url,
)


def _fake_getaddrinfo(addresses: list[str]) -> object:
    def fake_getaddrinfo(
        _host: str, _port: int | None, **kwargs: int
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        family = socket.AF_INET6 if ":" in addresses[0] else socket.AF_INET
        socket_type = kwargs["type"]
        return [(family, socket_type, 6, "", (address, 443)) for address in addresses]

    return fake_getaddrinfo


@pytest.mark.parametrize(
    ("url", "address"),
    [
        ("http://127.0.0.1/feed.xml", "127.0.0.1"),
        ("http://localhost/feed.xml", "127.0.0.1"),
        ("http://10.0.0.1/feed.xml", "10.0.0.1"),
        ("http://169.254.169.254/latest/meta-data", "169.254.169.254"),
        ("http://[::1]/feed.xml", "::1"),
        ("http://[fc00::1]/feed.xml", "fc00::1"),
    ],
)
def test_validate_server_fetch_url_rejects_unsafe_targets(
    url: str, address: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([address]))

    with pytest.raises(UnsafeUrlError):
        validate_server_fetch_url(url)


def test_validate_server_fetch_url_accepts_public_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34"]))

    validate_server_fetch_url("https://example.com/feed.xml")


def test_validate_server_fetch_url_rejects_any_unsafe_resolved_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34", "10.0.0.1"]))

    with pytest.raises(UnsafeUrlError):
        validate_server_fetch_url("https://example.com/feed.xml")


def test_redirect_handler_follows_safe_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34"]))
    handler = _ValidatingRedirectHandler()
    req = urllib.request.Request("https://example.com/feed.xml")

    result = handler.redirect_request(
        req,
        io.BytesIO(),
        301,
        "Moved Permanently",
        HTTPMessage(),
        "https://example.com/new-feed.xml",
    )

    assert result is not None
    assert result.full_url == "https://example.com/new-feed.xml"


def test_redirect_handler_blocks_redirect_to_private_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["169.254.169.254"]))
    handler = _ValidatingRedirectHandler()
    req = urllib.request.Request("https://example.com/feed.xml")

    result = handler.redirect_request(
        req, io.BytesIO(), 302, "Found", HTTPMessage(), "http://169.254.169.254/latest/meta-data"
    )

    assert result is None
