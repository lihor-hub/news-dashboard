from __future__ import annotations

import io
import socket
import ssl
import threading
import urllib.request
from collections.abc import Callable
from http.client import HTTPMessage
from typing import Any

import pytest

from news_dashboard.url_safety import (
    UnsafeUrlError,
    _ValidatingRedirectHandler,
    open_server_fetch_url,
    validate_server_fetch_url,
)

_SockAddr = tuple[str, int] | tuple[str, int, int, int]
_AddrInfo = tuple[int, int, int, str, _SockAddr]


def _fake_getaddrinfo(addresses: list[str]) -> Callable[..., list[_AddrInfo]]:
    def fake_getaddrinfo(_host: str, _port: int | None, **kwargs: int) -> list[_AddrInfo]:
        socket_type = kwargs["type"]
        port = _port or 0
        return [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket_type,
                socket.IPPROTO_TCP,
                "",
                (address, port, 0, 0) if ":" in address else (address, port),
            )
            for address in addresses
        ]

    return fake_getaddrinfo


class _SocketResponder:
    def __init__(self, responses: list[bytes]) -> None:
        self._responses = iter(responses)
        self.dials: list[tuple[str, int]] = []
        self.requests: list[bytes] = []
        self._threads: list[threading.Thread] = []

    def create_connection(
        self,
        address: tuple[str, int],
        timeout: object | None = None,
        source_address: tuple[str, int] | None = None,
        *,
        all_errors: bool = False,
    ) -> _SocketAdapter:
        del timeout, source_address, all_errors
        self.dials.append(address)
        response = next(self._responses)
        client, server = socket.socketpair()

        def respond() -> None:
            request = b""
            try:
                while b"\r\n\r\n" not in request:
                    request += server.recv(4096)
                self.requests.append(request)
                server.sendall(response)
            finally:
                server.close()

        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        self._threads.append(thread)
        return _SocketAdapter(client)

    def join(self) -> None:
        for thread in self._threads:
            thread.join(timeout=2)


class _SocketAdapter:
    """Socketpair endpoint that tolerates HTTPConnection's TCP_NODELAY setup."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def setsockopt(self, _level: int, _option: int, _value: int) -> None:
        return None

    def sendall(self, data: bytes) -> None:
        self._sock.sendall(data)

    def makefile(self, *args: Any, **kwargs: Any) -> Any:
        return self._sock.makefile(*args, **kwargs)

    def close(self) -> None:
        self._sock.close()


def _ok_response(body: bytes = b"ok") -> bytes:
    return b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


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


@pytest.mark.parametrize(
    ("url", "resolved_address", "expected_dial", "expected_host"),
    [
        (
            "http://example.test/feed.xml",
            "93.184.216.34",
            ("93.184.216.34", 80),
            b"Host: example.test\r\n",
        ),
        (
            "http://example.test:8080/feed.xml",
            "93.184.216.34",
            ("93.184.216.34", 8080),
            b"Host: example.test:8080\r\n",
        ),
        (
            "http://[2606:4700:4700::1111]:8080/feed.xml",
            "2606:4700:4700::1111",
            ("2606:4700:4700::1111", 8080),
            b"Host: [2606:4700:4700::1111]:8080\r\n",
        ),
    ],
)
def test_open_dials_the_validated_numeric_address_without_second_dns_lookup(
    url: str,
    resolved_address: str,
    expected_dial: tuple[str, int],
    expected_host: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver_calls: list[tuple[str, int | None]] = []

    def resolve_once(host: str, port: int | None, **kwargs: int) -> list[_AddrInfo]:
        resolver_calls.append((host, port))
        if len(resolver_calls) > 1:
            msg = "hostname was resolved more than once"
            raise AssertionError(msg)
        return _fake_getaddrinfo([resolved_address])(host, port, **kwargs)

    responder = _SocketResponder([_ok_response()])
    monkeypatch.setattr(socket, "getaddrinfo", resolve_once)
    monkeypatch.setattr(socket, "create_connection", responder.create_connection)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:3128")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:3128")

    request = urllib.request.Request(url)  # noqa: S310 - validated by open_server_fetch_url
    with open_server_fetch_url(request, timeout=1) as response:
        assert response.read() == b"ok"
    responder.join()

    assert len(resolver_calls) == 1
    assert responder.dials == [expected_dial]
    assert expected_host in responder.requests[0]


def test_trailing_dot_is_canonicalized_only_for_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_hosts: list[str] = []

    def resolve(
        host: str, port: int | None, **kwargs: int
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        resolved_hosts.append(host)
        return [
            (
                socket.AF_INET,
                kwargs["type"],
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", port or 0),
            )
        ]

    responder = _SocketResponder([_ok_response()])
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket, "create_connection", responder.create_connection)

    request = urllib.request.Request("http://Example.Test.:8080/feed.xml")
    with open_server_fetch_url(request, timeout=1) as response:
        response.read()
    responder.join()

    assert resolved_hosts == ["example.test"]
    assert responder.dials == [("93.184.216.34", 8080)]
    assert b"Host: Example.Test.:8080\r\n" in responder.requests[0]


def test_https_uses_original_hostname_for_sni(monkeypatch: pytest.MonkeyPatch) -> None:
    responder = _SocketResponder([_ok_response()])
    server_hostnames: list[str | None] = []

    def wrap_socket(
        _context: ssl.SSLContext,
        sock: _SocketAdapter,
        *,
        server_hostname: str | None = None,
        **_kwargs: Any,
    ) -> _SocketAdapter:
        server_hostnames.append(server_hostname)
        return sock

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34"]))
    monkeypatch.setattr(socket, "create_connection", responder.create_connection)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap_socket)

    request = urllib.request.Request("https://example.test:8443/feed.xml")
    with open_server_fetch_url(request, timeout=1) as response:
        response.read()
    responder.join()

    assert responder.dials == [("93.184.216.34", 8443)]
    assert server_hostnames == ["example.test"]
    assert b"Host: example.test:8443\r\n" in responder.requests[0]


def test_redirect_resolves_validates_and_pins_each_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver_calls: list[tuple[str, int | None]] = []

    def resolve(
        host: str, port: int | None, **kwargs: int
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        resolver_calls.append((host, port))
        address = "93.184.216.34" if host == "example.test" else "169.254.169.254"
        return [(socket.AF_INET, kwargs["type"], socket.IPPROTO_TCP, "", (address, port or 0))]

    redirect = (
        b"HTTP/1.1 302 Found\r\n"
        b"Location: http://metadata.test/latest/meta-data\r\n"
        b"Content-Length: 0\r\n\r\n"
    )
    responder = _SocketResponder([redirect])
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket, "create_connection", responder.create_connection)

    request = urllib.request.Request("http://example.test/feed.xml")
    with pytest.raises(UnsafeUrlError):
        open_server_fetch_url(request, timeout=1)
    responder.join()

    assert resolver_calls == [("example.test", 80), ("metadata.test", 80)]
    assert responder.dials == [("93.184.216.34", 80)]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test:not-a-port/feed.xml",
        "http://user:password@example.test/feed.xml",
        "http://example.test/\nheader",
        "http://example.test/\x00control",
    ],
)
def test_validate_rejects_malformed_ports_userinfo_and_control_characters(
    url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_dns(*_args: object, **_kwargs: object) -> None:
        msg = "malformed URL reached DNS resolution"
        raise AssertionError(msg)

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_dns)

    with pytest.raises(UnsafeUrlError):
        validate_server_fetch_url(url)


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

    with pytest.raises(UnsafeUrlError):
        handler.redirect_request(
            req,
            io.BytesIO(),
            302,
            "Found",
            HTTPMessage(),
            "http://169.254.169.254/latest/meta-data",
        )
