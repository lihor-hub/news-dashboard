from __future__ import annotations

import asyncio

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Mount


def test_mcp_http_config_uses_safe_local_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.mcp.config import McpHttpConfig

    for name in ("APP_BASE_URL", "MCP_ALLOWED_HOSTS", "MCP_ALLOWED_ORIGINS"):
        monkeypatch.delenv(name, raising=False)

    config = McpHttpConfig.from_environment()

    assert config.allowed_hosts == ("localhost:8080", "127.0.0.1:8080", "[::1]:8080")
    assert config.allowed_origins == (
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://[::1]:8080",
    )


def test_mcp_http_config_derives_exact_values_from_public_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.mcp.config import McpHttpConfig

    monkeypatch.setenv("APP_BASE_URL", "https://news.example.com/dashboard")
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("MCP_ALLOWED_ORIGINS", raising=False)

    config = McpHttpConfig.from_environment()

    assert config.allowed_hosts == ("news.example.com",)
    assert config.allowed_origins == ("https://news.example.com",)


def test_mcp_http_config_explicit_allowlists_override_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.mcp.config import McpHttpConfig

    monkeypatch.setenv("APP_BASE_URL", "https://ignored.example.com")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "news.example.com, news.internal:8080")
    monkeypatch.setenv(
        "MCP_ALLOWED_ORIGINS",
        "https://news.example.com,https://admin.example.com",
    )

    config = McpHttpConfig.from_environment()

    assert config.allowed_hosts == ("news.example.com", "news.internal:8080")
    assert config.allowed_origins == (
        "https://news.example.com",
        "https://admin.example.com",
    )


def test_mcp_http_config_rejects_wildcards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.mcp.config import McpHttpConfig

    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "*.example.com")

    with pytest.raises(ValueError, match="exact values"):
        McpHttpConfig.from_environment()


def test_mcp_http_app_factory_enforces_host_and_origin() -> None:
    from news_dashboard.mcp.config import McpHttpConfig
    from news_dashboard.mcp.server import create_mcp_http_app, mcp

    config = McpHttpConfig(
        allowed_hosts=("news.example.com",),
        allowed_origins=("https://news.example.com",),
    )
    guarded_app = create_mcp_http_app(mcp, config=config)
    outer_app = Starlette(routes=[Mount("/mcp", app=guarded_app)])

    async def request(*, host: str, origin: str | None = None) -> httpx.Response:
        headers = {"host": host, "accept": "application/json, text/event-stream"}
        if origin is not None:
            headers["origin"] = origin
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=outer_app),
            base_url="https://internal.test",
        ) as client:
            return await client.post("/mcp/", headers=headers, json={})

    allowed = asyncio.run(request(host="news.example.com"))
    bad_host = asyncio.run(request(host="evil.example.com"))
    implicit_local_host = asyncio.run(request(host="testserver"))
    bad_origin = asyncio.run(request(host="news.example.com", origin="https://evil.example.com"))
    wrong_scheme = asyncio.run(request(host="news.example.com", origin="http://news.example.com"))

    assert allowed.status_code != 421
    assert bad_host.status_code == 421
    assert implicit_local_host.status_code == 421
    assert bad_origin.status_code == 403
    assert wrong_scheme.status_code == 403
    assert bad_host.text == "Misdirected Request"
    assert bad_origin.text == "Forbidden"
