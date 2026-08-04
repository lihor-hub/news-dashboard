"""Deployed-front-door integration coverage for the mounted FastMCP server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp.shared.exceptions import McpError

from news_dashboard.db import connect
from news_dashboard.main import app

_ALL_TOOLS = {
    "ask_news",
    "get_briefing",
    "get_news_article",
    "list_briefings",
    "list_latest_news",
    "list_news_sources",
    "search_news",
}


def _make_user(database_url: str, username: str) -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'hash') RETURNING id",
            (username,),
        ).fetchone()
    return int(row["id"])


def _seed_private_news(database_url: str, user_id: int, *, slug: str, article_id: int) -> None:
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(
                slug, name, url, category, kind, priority, enabled, owner_user_id
            ) VALUES (%s, %s, %s, 'engineering', 'rss', 50, TRUE, %s)
            """,
            (slug, slug, f"https://example.test/{slug}.xml", user_id),
        )
        conn.execute(
            """
            INSERT INTO articles(
                id, url, canonical_url, title, source_slug, source_name,
                category, kind, status, importance_score, summary, reason, tags,
                body, body_status
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                'engineering', 'rss', 'new', 0.8, %s, '', '', %s, 'ok'
            )
            """,
            (
                article_id,
                f"https://example.test/articles/{article_id}",
                f"https://example.test/articles/{article_id}",
                f"Private article {article_id}",
                slug,
                slug,
                f"Private summary {article_id}",
                f"Private body {article_id}",
            ),
        )
        conn.execute(
            """
            INSERT INTO user_article_state(user_id, article_id, state, starred)
            VALUES (%s, %s, 'done', TRUE)
            """,
            (user_id, article_id),
        )


def _seed_briefing(database_url: str, user_id: int, *, title: str) -> int:
    content = {
        "sections": [{"title": "Top", "body": "Saved body", "citations": []}],
        "worth_opening": [],
    }
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(
                title, summary, content, status, scope, model, user_id
            ) VALUES (%s, 'Saved summary', %s::jsonb, 'complete', 'day', 'model', %s)
            RETURNING id
            """,
            (title, json.dumps(content), user_id),
        ).fetchone()
    return int(row["id"])


@asynccontextmanager
async def _mounted_client(token: str | None) -> AsyncIterator[Client[Any]]:
    """Use the official client through the real FastAPI route table."""
    from news_dashboard.mcp.server import mcp_http_app

    def client_factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
        *,
        follow_redirects: bool = True,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost:8080",
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=follow_redirects,
        )

    transport = StreamableHttpTransport(
        "http://localhost:8080/mcp/",
        auth=token,
        httpx_client_factory=client_factory,
    )
    client_error: BaseException | None = None
    async with mcp_http_app.router.lifespan_context(mcp_http_app):
        try:
            async with Client(transport) as client:
                yield client
        except BaseException as exc:
            client_error = exc
    if client_error is not None:
        raise client_error


def test_mounted_fastapi_exposes_complete_catalog_and_representative_workflow(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    user_id = _make_user(pg_clean, "mcp-mounted-complete")
    _seed_private_news(pg_clean, user_id, slug="mounted-private", article_id=81_001)
    briefing_id = _seed_briefing(pg_clean, user_id, title="Mounted briefing")
    created = service.create_token(user_id, "mounted-client", database_url=pg_clean)
    captured: dict[str, Any] = {}

    def offline_ask(question: str, **kwargs: Any) -> dict[str, Any]:
        captured.update({"question": question, **kwargs})
        return {
            "answer": "The private article is relevant [1].",
            "sources": [
                {
                    "id": 81_001,
                    "title": "Private article 81001",
                    "url": "https://example.test/articles/81001",
                }
            ],
            "trace_id": None,
        }

    monkeypatch.setattr("news_dashboard.assistant.service.ask", offline_ask)

    async def exercise() -> None:
        async with _mounted_client(created["token"]) as client:
            assert {tool.name for tool in await client.list_tools()} == _ALL_TOOLS

            latest = await client.call_tool("list_latest_news", {"limit": 1})
            article = await client.call_tool("get_news_article", {"article_id": 81_001})
            briefings = await client.call_tool("list_briefings", {"limit": 1})
            briefing = await client.call_tool("get_briefing", {"briefing_id": briefing_id})
            answer = await client.call_tool(
                "ask_news",
                {"question": "What is relevant?", "corpus": "saved_and_read"},
            )

        assert latest.structured_content is not None
        assert latest.structured_content["articles"][0]["id"] == 81_001
        assert article.structured_content is not None
        assert article.structured_content["article"]["body"] == "Private body 81001"
        assert briefings.structured_content is not None
        assert briefings.structured_content["briefings"][0]["id"] == briefing_id
        assert briefing.structured_content is not None
        assert briefing.structured_content["briefing"]["id"] == briefing_id
        assert answer.structured_content == {
            "answer": "The private article is relevant [1].",
            "citations": [
                {
                    "id": 81_001,
                    "title": "Private article 81001",
                    "url": "https://example.test/articles/81001",
                }
            ],
            "trace_id": None,
            "truncated": False,
        }

    asyncio.run(exercise())
    assert captured["question"] == "What is relevant?"
    assert captured["include_all"] is False
    assert captured["user_id"] == user_id


def test_mounted_fastapi_preserves_scope_revocation_and_cross_user_isolation(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "mcp-mounted-alice")
    bob = _make_user(pg_clean, "mcp-mounted-bob")
    _seed_private_news(pg_clean, bob, slug="bob-mounted-private", article_id=81_002)
    bob_briefing = _seed_briefing(pg_clean, bob, title="Bob private briefing")
    alice_token = service.create_token(alice, "alice-read", scopes=("read",), database_url=pg_clean)

    async def exercise() -> None:
        async with _mounted_client(alice_token["token"]) as client:
            assert [tool.name for tool in await client.list_tools()] == ["get_news_article"]
            hidden_article = await client.call_tool("get_news_article", {"article_id": 81_002})
            denied_briefing = await client.call_tool(
                "get_briefing", {"briefing_id": bob_briefing}, raise_on_error=False
            )
        assert hidden_article.structured_content == {
            "found": False,
            "article": None,
            "truncated": False,
        }
        assert denied_briefing.is_error is True

        service.revoke_token(alice, alice_token["id"], database_url=pg_clean)
        with pytest.raises(httpx.HTTPStatusError) as revoked:
            async with _mounted_client(alice_token["token"]):
                pass
        assert revoked.value.response.status_code == 401

        for unavailable in (None, "ndmcp_invalid-mounted-token"):
            with pytest.raises(httpx.HTTPStatusError) as rejected:
                async with _mounted_client(unavailable):
                    pass
            assert rejected.value.response.status_code == 401

    asyncio.run(exercise())


@pytest.mark.smoke
def test_application_front_door_reserves_mcp_before_spa_and_enforces_transport_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    client = TestClient(app, follow_redirects=False)
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "front-door-smoke", "version": "1"},
        },
    }
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
        "host": "localhost:8080",
        "mcp-protocol-version": "2025-06-18",
    }

    missing_auth = client.post("/mcp/", json=initialize, headers=headers)
    assert missing_auth.status_code == 401
    assert "text/html" not in missing_auth.headers.get("content-type", "")
    assert "<!doctype html" not in missing_auth.text.lower()

    bad_host = client.post(
        "/mcp/", json=initialize, headers={**headers, "host": "attacker.example"}
    )
    assert bad_host.status_code == 421

    bad_origin = client.post(
        "/mcp/",
        json=initialize,
        headers={**headers, "origin": "https://attacker.example"},
    )
    assert bad_origin.status_code == 403

    monkeypatch.setenv("MCP_SERVER_ENABLED", "false")
    disabled = client.post("/mcp/", json=initialize, headers=headers)
    assert disabled.status_code == 404
    assert "<!doctype html" not in disabled.text.lower()


def test_disabled_mounted_client_cannot_initialize(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    user_id = _make_user(pg_clean, "mcp-mounted-disabled")
    token = service.create_token(user_id, "disabled", database_url=pg_clean)["token"]
    monkeypatch.setenv("MCP_SERVER_ENABLED", "false")

    async def exercise() -> None:
        with pytest.raises(McpError):
            async with _mounted_client(token):
                pass

    asyncio.run(exercise())
