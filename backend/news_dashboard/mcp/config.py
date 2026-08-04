from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

_LOCAL_HOSTS = ("localhost:8080", "127.0.0.1:8080", "[::1]:8080")
_LOCAL_ORIGINS = (
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://[::1]:8080",
)


def _comma_separated_environment(name: str) -> tuple[str, ...] | None:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return None
    values = tuple(value.strip() for value in raw_value.split(",") if value.strip())
    if any("*" in value for value in values):
        message = f"{name} must contain exact values; wildcards are not allowed"
        raise ValueError(message)
    return values


def _public_host_and_origin() -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    public_base_url = (os.getenv("APP_BASE_URL") or "").strip()
    if not public_base_url:
        return None
    parsed = urlsplit(public_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        message = "APP_BASE_URL must be an absolute HTTP(S) URL when used for MCP protection"
        raise ValueError(message)
    return (parsed.netloc,), (f"{parsed.scheme}://{parsed.netloc}",)


@dataclass(frozen=True, slots=True)
class McpHttpConfig:
    """Exact Host and Origin values accepted by the MCP HTTP transport."""

    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> McpHttpConfig:
        public_values = _public_host_and_origin()
        default_hosts, default_origins = public_values or (_LOCAL_HOSTS, _LOCAL_ORIGINS)
        return cls(
            allowed_hosts=_comma_separated_environment("MCP_ALLOWED_HOSTS") or default_hosts,
            allowed_origins=_comma_separated_environment("MCP_ALLOWED_ORIGINS") or default_origins,
        )
