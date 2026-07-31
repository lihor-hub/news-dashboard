"""Server-side fetch target validation.

The application fetches user-controlled feed and article URLs from backend
workers.  Validate those targets before network I/O so a malicious source cannot
reach localhost, private networks, or cloud metadata services from the server.
"""

from __future__ import annotations

import concurrent.futures
import functools
import http.client
import ipaddress
import socket
import ssl
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from http.client import HTTPMessage
from typing import IO, Any, cast
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    """Raised when a URL is not safe for server-side fetching."""


_SockAddr = tuple[str, int] | tuple[str, int, int, int]
_DNS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="server-fetch-dns",
)
_DNS_ADMISSION = threading.BoundedSemaphore(value=4)


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    """A validated numeric endpoint for one HTTP request."""

    hostname: str
    dns_hostname: str
    sockaddr: _SockAddr
    family: int
    protocol: int


def validate_server_fetch_url(url: str) -> None:
    """Raise UnsafeUrlError if ``url`` is not safe for backend network fetches."""
    _resolve_server_fetch_target(url)


def _parse_server_fetch_url(url: str) -> tuple[str, str, int]:
    """Return the original host, normalized DNS host, and effective port."""
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        msg = f"Refusing to fetch URL containing control characters: {url!r}"
        raise UnsafeUrlError(msg)

    try:
        parsed = urlparse(url.strip())
        hostname = parsed.hostname
        parsed_port = parsed.port
        username = parsed.username
        password = parsed.password
    except ValueError as exc:
        msg = f"Refusing to fetch malformed URL: {url!r}"
        raise UnsafeUrlError(msg) from exc

    if parsed.scheme not in {"http", "https"}:
        msg = f"Refusing to fetch non-HTTP URL: {url!r}"
        raise UnsafeUrlError(msg)

    if not hostname:
        msg = f"Refusing to fetch URL without a host: {url!r}"
        raise UnsafeUrlError(msg)

    if username is not None or password is not None:
        msg = f"Refusing to fetch URL containing user information: {url!r}"
        raise UnsafeUrlError(msg)

    normalized_host = hostname.rstrip(".").lower()
    if not normalized_host:
        msg = f"Refusing to fetch URL without a valid host: {url!r}"
        raise UnsafeUrlError(msg)

    if normalized_host in {"localhost", "localhost.localdomain"} or normalized_host.endswith(
        ".localhost"
    ):
        msg = f"Refusing to fetch local host: {hostname!r}"
        raise UnsafeUrlError(msg)

    port = (443 if parsed.scheme == "https" else 80) if parsed_port is None else parsed_port
    if port <= 0:
        msg = f"Refusing to fetch URL with invalid port: {url!r}"
        raise UnsafeUrlError(msg)
    return hostname, normalized_host, port


def _remaining_timeout(deadline: float | None, timeout: float | None) -> float | None:
    if deadline is None:
        return timeout
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        message = "Server fetch deadline exceeded"
        raise TimeoutError(message)
    return remaining if timeout is None else min(timeout, remaining)


def _resolve_server_fetch_target(
    url: str,
    *,
    deadline: float | None = None,
) -> ResolvedTarget:
    """Resolve and validate every answer, then select one numeric endpoint."""
    hostname, normalized_host, port = _parse_server_fetch_url(url)
    try:
        addresses = _getaddrinfo_before_deadline(
            normalized_host,
            port,
            deadline,
        )
    except socket.gaierror as exc:
        msg = f"Could not resolve fetch host: {hostname!r}"
        raise UnsafeUrlError(msg) from exc

    selected: ResolvedTarget | None = None
    for family, _, protocol, _, sockaddr in addresses:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            msg = f"Refusing to fetch unsupported address family: {family}"
            raise UnsafeUrlError(msg)

        raw_address = sockaddr[0]
        try:
            ip = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            msg = f"Could not classify fetch address: {raw_address!r}"
            raise UnsafeUrlError(msg) from exc

        if _is_unsafe_ip(ip):
            msg = f"Refusing to fetch unsafe host address: {ip}"
            raise UnsafeUrlError(msg)

        if selected is None:
            pinned_sockaddr: _SockAddr
            if family == socket.AF_INET6:
                ipv6_sockaddr = cast("tuple[str, int, int, int]", sockaddr)
                pinned_sockaddr = (str(ip), port, ipv6_sockaddr[2], ipv6_sockaddr[3])
            else:
                pinned_sockaddr = (str(ip), port)
            selected = ResolvedTarget(
                hostname=hostname,
                dns_hostname=normalized_host,
                sockaddr=pinned_sockaddr,
                family=family,
                protocol=protocol,
            )

    if selected is None:
        msg = f"Could not resolve fetch host: {hostname!r}"
        raise UnsafeUrlError(msg)
    return selected


def _getaddrinfo_before_deadline(
    hostname: str,
    port: int,
    deadline: float | None,
) -> list[tuple[Any, ...]]:
    if deadline is None:
        return socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    future = _submit_dns_resolution(
        socket.getaddrinfo,
        hostname,
        port,
        type=socket.SOCK_STREAM,
    )
    try:
        return cast(
            "list[tuple[Any, ...]]",
            future.result(timeout=_remaining_timeout(deadline, None)),
        )
    except concurrent.futures.TimeoutError as exc:
        if future.cancel():
            _DNS_ADMISSION.release()
        message = "Server fetch deadline exceeded"
        raise TimeoutError(message) from exc


def _submit_dns_resolution(
    function: Any,
    *args: Any,
    **kwargs: Any,
) -> concurrent.futures.Future[Any]:
    """Submit DNS work only when a worker slot is immediately available."""
    if not _DNS_ADMISSION.acquire(blocking=False):
        message = "Server fetch DNS capacity exhausted"
        raise TimeoutError(message)
    try:
        return _DNS_EXECUTOR.submit(
            _run_admitted_dns_resolution,
            function,
            args,
            kwargs,
        )
    except RuntimeError:
        _DNS_ADMISSION.release()
        raise


def _run_admitted_dns_resolution(
    function: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    try:
        return function(*args, **kwargs)
    finally:
        _DNS_ADMISSION.release()


@dataclass(slots=True)
class _ResolvedTargetStore:
    targets: dict[urllib.request.Request, ResolvedTarget] = field(default_factory=dict)
    deadline: float | None = None

    def add(self, request: urllib.request.Request, target: ResolvedTarget) -> None:
        self.targets[request] = target

    def get(self, request: urllib.request.Request) -> ResolvedTarget:
        target = self.targets.get(request)
        if target is None:
            target = _resolve_server_fetch_target(
                request.full_url,
                deadline=self.deadline,
            )
            self.add(request, target)
        return target


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only after re-validating each hop against SSRF rules.

    urllib validates the *initial* fetch target, but a 3xx response can point
    anywhere — including localhost or a cloud metadata endpoint. Re-validate
    every redirect target before following it. Returning ``None`` for an unsafe
    hop makes urllib raise the underlying ``HTTPError`` instead of chasing the
    redirect, so the caller sees a fetch failure rather than reaching a private
    host. urllib's built-in redirect cap (``max_redirections``) still applies.
    """

    def __init__(self, targets: _ResolvedTargetStore | None = None) -> None:
        super().__init__()
        self._targets = targets or _ResolvedTargetStore()

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        target = _resolve_server_fetch_target(
            newurl,
            deadline=self._targets.deadline,
        )
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            self._targets.add(redirected, target)
        return redirected


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Return redirect responses to the caller instead of following them."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> None:
        _ = req, fp, code, msg, headers, newurl


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(
        self,
        host: str,
        *,
        resolved_target: ResolvedTarget,
        deadline: float | None,
        **kwargs: Any,
    ) -> None:
        super().__init__(host, **kwargs)
        self._resolved_target = resolved_target
        self._deadline = deadline

    def connect(self) -> None:
        """Connect to the validated numeric address, retaining ``self.host``."""
        self.sock = _connect_resolved_target(
            self._resolved_target,
            _remaining_timeout(self._deadline, self.timeout),
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        *,
        resolved_target: ResolvedTarget,
        deadline: float | None,
        context: ssl.SSLContext | None = None,
        **kwargs: Any,
    ) -> None:
        ssl_context = context or ssl.create_default_context()
        super().__init__(host, context=ssl_context, **kwargs)
        self._resolved_target = resolved_target
        self._deadline = deadline
        self._ssl_context = ssl_context

    def connect(self) -> None:
        """Dial the numeric address and authenticate the original hostname."""
        self.sock = _connect_resolved_target(
            self._resolved_target,
            _remaining_timeout(self._deadline, self.timeout),
        )
        self.sock = self._ssl_context.wrap_socket(
            self.sock,
            server_hostname=self._resolved_target.dns_hostname,
        )


def _connect_resolved_target(
    target: ResolvedTarget,
    timeout: float | None,
) -> socket.socket:
    """Connect a socket directly to the validated sockaddr without name lookup."""
    sock = socket.socket(target.family, socket.SOCK_STREAM, target.protocol)
    try:
        sock.settimeout(timeout)
        sock.connect(target.sockaddr)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        sock.close()
        raise
    return sock


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, targets: _ResolvedTargetStore) -> None:
        super().__init__()
        self._targets = targets

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        target = self._targets.get(req)
        connection = functools.partial(
            _PinnedHTTPConnection,
            resolved_target=target,
            deadline=self._targets.deadline,
        )
        return self.do_open(connection, req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(
        self,
        targets: _ResolvedTargetStore,
        context: ssl.SSLContext | None = None,
    ) -> None:
        ssl_context = context or ssl.create_default_context()
        super().__init__(context=ssl_context)
        self._targets = targets
        self._ssl_context = ssl_context

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        target = self._targets.get(req)
        connection = functools.partial(
            _PinnedHTTPSConnection,
            resolved_target=target,
            deadline=self._targets.deadline,
        )
        return self.do_open(connection, req, context=self._ssl_context)


def open_server_fetch_url(
    request: urllib.request.Request,
    *,
    timeout: float,
    deadline: float | None = None,
    follow_redirects: bool = True,
) -> Any:
    """Open a prevalidated server-side fetch request, following only safe redirects."""
    target = _resolve_server_fetch_target(request.full_url, deadline=deadline)
    targets = _ResolvedTargetStore(deadline=deadline)
    targets.add(request, target)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _PinnedHTTPHandler(targets),
        _PinnedHTTPSHandler(targets),
        (_ValidatingRedirectHandler(targets) if follow_redirects else _RejectRedirectHandler()),
    )
    return opener.open(
        request,
        timeout=_remaining_timeout(deadline, timeout),
    )


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        not ip.is_global
        or ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
