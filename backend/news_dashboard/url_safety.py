"""Server-side fetch target validation.

The application fetches user-controlled feed and article URLs from backend
workers.  Validate those targets before network I/O so a malicious source cannot
reach localhost, private networks, or cloud metadata services from the server.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.request
from http.client import HTTPMessage
from typing import IO, Any
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    """Raised when a URL is not safe for server-side fetching."""


def validate_server_fetch_url(url: str) -> None:
    """Raise UnsafeUrlError if ``url`` is not safe for backend network fetches."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        msg = f"Refusing to fetch non-HTTP URL: {url!r}"
        raise UnsafeUrlError(msg)

    hostname = parsed.hostname
    if not hostname:
        msg = f"Refusing to fetch URL without a host: {url!r}"
        raise UnsafeUrlError(msg)

    normalized_host = hostname.rstrip(".").lower()
    if normalized_host in {"localhost", "localhost.localdomain"} or normalized_host.endswith(
        ".localhost"
    ):
        msg = f"Refusing to fetch local host: {hostname!r}"
        raise UnsafeUrlError(msg)

    try:
        addresses = socket.getaddrinfo(normalized_host, parsed.port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        msg = f"Could not resolve fetch host: {hostname!r}"
        raise UnsafeUrlError(msg) from exc

    for family, _, _, _, sockaddr in addresses:
        raw_address = sockaddr[0]
        try:
            ip = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            msg = f"Could not classify fetch address: {raw_address!r}"
            raise UnsafeUrlError(msg) from exc

        if _is_unsafe_ip(ip):
            msg = f"Refusing to fetch unsafe host address: {ip}"
            raise UnsafeUrlError(msg)

        if family not in {socket.AF_INET, socket.AF_INET6}:
            msg = f"Refusing to fetch unsupported address family: {family}"
            raise UnsafeUrlError(msg)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        _ = (req, fp, code, msg, headers, newurl)
        return None


def open_server_fetch_url(request: urllib.request.Request, *, timeout: float) -> Any:
    """Open a prevalidated server-side fetch request without following redirects."""
    validate_server_fetch_url(request.full_url)
    opener = urllib.request.build_opener(_NoRedirectHandler)
    return opener.open(request, timeout=timeout)


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
