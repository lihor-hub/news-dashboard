from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from threading import Event
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp.shared.exceptions import McpError
from mcp.types import TextContent
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Message, Receive, Scope, Send

from news_dashboard.db import connect
from news_dashboard.main import app


def _make_user(database_url: str, username: str) -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'hash') RETURNING id",
            (username,),
        ).fetchone()
    return int(row["id"])


def _seed_source(
    database_url: str, slug: str = "test-source", *, owner_user_id: int | None = None
) -> None:
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(
                slug, name, url, category, kind, priority, enabled, owner_user_id
            )
            VALUES (%s, %s, %s, 'engineering', 'rss', 50, TRUE, %s)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug, f"https://example.com/{slug}.xml", owner_user_id),
        )


def _seed_article(database_url: str, article_id: int, source_slug: str = "test-source") -> None:
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO articles(
                id, url, canonical_url, title, source_slug, source_name,
                category, kind, status, importance_score, summary, reason, tags
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                article_id,
                f"https://example.com/{article_id}",
                f"https://example.com/{article_id}",
                f"Article {article_id}",
                source_slug,
                source_slug,
                "engineering",
                "rss",
                "new",
                0.5,
                f"Summary {article_id}",
                "",
                "",
            ),
        )


# ─── service.py — token lifecycle ────────────────────────────────────────────


def test_create_list_revoke_tokens_scoped_to_user(pg_clean: str) -> None:
    from news_dashboard.mcp import service

    alice = _make_user(pg_clean, "alice-mcp")
    bob = _make_user(pg_clean, "bob-mcp")

    created = service.create_token(alice, "Claude Desktop", database_url=pg_clean)
    assert created["token"].startswith(service.TOKEN_PREFIX)
    assert created["token_prefix"] in created["token"]

    assert [t["id"] for t in service.list_tokens(alice, database_url=pg_clean)] == [created["id"]]
    assert service.list_tokens(bob, database_url=pg_clean) == []

    # bob cannot revoke alice's token
    assert service.revoke_token(bob, created["id"], database_url=pg_clean) is None
    revoked = service.revoke_token(alice, created["id"], database_url=pg_clean)
    assert revoked is not None
    assert revoked["revoked_at"] is not None


def test_created_token_response_never_stores_plaintext(pg_clean: str) -> None:
    from news_dashboard.mcp import service

    alice = _make_user(pg_clean, "alice-hash")
    created = service.create_token(alice, "client", database_url=pg_clean)

    listed = service.list_tokens(alice, database_url=pg_clean)[0]
    assert "token" not in listed
    assert "token_hash" not in listed
    assert listed["token_prefix"] == created["token_prefix"]


def test_token_limit_per_user(pg_clean: str) -> None:
    from news_dashboard.mcp import service

    alice = _make_user(pg_clean, "alice-limit")
    for i in range(service.MAX_TOKENS_PER_USER):
        service.create_token(alice, f"client-{i}", database_url=pg_clean)

    with pytest.raises(ValueError, match="token limit reached"):
        service.create_token(alice, "one-too-many", database_url=pg_clean)


def test_authenticate_token_rejects_unknown_revoked_and_malformed(pg_clean: str) -> None:
    from news_dashboard.mcp import service

    alice = _make_user(pg_clean, "alice-auth")
    created = service.create_token(alice, "client", database_url=pg_clean)
    token = created["token"]

    auth = service.authenticate_token(token, database_url=pg_clean)
    assert auth is not None
    assert auth["user_id"] == alice
    assert auth["scopes"] == set(service.DEFAULT_SCOPES)

    assert service.authenticate_token("not-a-real-token", database_url=pg_clean) is None
    assert service.authenticate_token("", database_url=pg_clean) is None

    service.revoke_token(alice, created["id"], database_url=pg_clean)
    assert service.authenticate_token(token, database_url=pg_clean) is None


def test_mcp_enabled_defaults_to_true(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.mcp import service

    monkeypatch.delenv("MCP_SERVER_ENABLED", raising=False)
    assert service.mcp_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off"])
def test_mcp_enabled_explicit_false_values_disable_server(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("MCP_SERVER_ENABLED", value)
    assert service.mcp_enabled() is False


def test_token_verifier_returns_expected_access_token(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service
    from news_dashboard.mcp.auth import NewsDashboardTokenVerifier

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean, "alice-verifier")
    created = service.create_token(
        user_id,
        "verifier",
        scopes=("read", "ask"),
        database_url=pg_clean,
    )

    verified = asyncio.run(NewsDashboardTokenVerifier().verify_token(created["token"]))

    assert verified is not None
    assert verified.token == created["token"]
    assert verified.subject == str(user_id)
    assert verified.client_id == f"mcp-token:{created['id']}"
    assert verified.scopes == ["ask", "read"]
    assert verified.claims["user_id"] == user_id
    assert verified.claims["token_id"] == created["id"]
    assert str(verified.claims["rate_limit_id"]).startswith("mcp-rate:")


def test_reused_database_token_id_gets_fresh_opaque_rate_limit_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.mcp import service
    from news_dashboard.mcp.auth import NewsDashboardTokenVerifier
    from news_dashboard.mcp.server import _BoundedTokenBuckets

    monkeypatch.setattr(
        service,
        "authenticate_token",
        lambda _token: {"token_id": 7, "user_id": 11, "scopes": {"search"}},
    )
    first_value = service.TOKEN_PREFIX + ("a" * 32)
    second_value = service.TOKEN_PREFIX + ("b" * 32)

    async def exercise() -> None:
        verifier = NewsDashboardTokenVerifier()
        first = await verifier.verify_token(first_value)
        second = await verifier.verify_token(second_value)
        assert first is not None
        assert second is not None
        assert first.client_id == second.client_id == "mcp-token:7"
        first_identity = str(first.claims["rate_limit_id"])
        second_identity = str(second.claims["rate_limit_id"])
        assert first_identity != second_identity
        assert first_value not in first_identity
        assert second_value not in second_identity

        buckets = _BoundedTokenBuckets(max_identities=3, capacity=1, refill_rate=0.0001)
        assert await buckets.for_client(first_identity).consume() is True
        assert await buckets.for_client(first_identity).consume() is False
        assert await buckets.for_client(second_identity).consume() is True

    asyncio.run(exercise())


@pytest.mark.parametrize("token", ["not-a-real-token", ""])
def test_token_verifier_rejects_malformed_tokens(token: str) -> None:
    from news_dashboard.mcp.auth import NewsDashboardTokenVerifier

    assert asyncio.run(NewsDashboardTokenVerifier().verify_token(token)) is None


def test_token_verifier_rejects_unknown_token(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service
    from news_dashboard.mcp.auth import NewsDashboardTokenVerifier

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    unknown_token = f"{service.TOKEN_PREFIX}not-issued"

    assert asyncio.run(NewsDashboardTokenVerifier().verify_token(unknown_token)) is None


def test_token_verifier_rejects_revoked_token(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service
    from news_dashboard.mcp.auth import NewsDashboardTokenVerifier

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean, "alice-verifier-revoked")
    created = service.create_token(user_id, "verifier", database_url=pg_clean)
    service.revoke_token(user_id, created["id"], database_url=pg_clean)

    assert asyncio.run(NewsDashboardTokenVerifier().verify_token(created["token"])) is None


def test_token_verifier_keeps_event_loop_responsive(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.mcp import service
    from news_dashboard.mcp.auth import NewsDashboardTokenVerifier

    authentication_started = Event()
    event_loop_progressed = Event()

    def slow_authenticate(_token: str) -> None:
        authentication_started.set()
        if not event_loop_progressed.wait(timeout=1):
            message = "authentication blocked the event loop"
            raise RuntimeError(message)

    monkeypatch.setattr(service, "authenticate_token", slow_authenticate)

    async def exercise_verifier() -> None:
        async def mark_event_loop_progress() -> None:
            while not authentication_started.is_set():
                await asyncio.sleep(0)
            event_loop_progressed.set()

        verified, _ = await asyncio.gather(
            NewsDashboardTokenVerifier().verify_token("ndmcp_slow"),
            mark_event_loop_progress(),
        )
        assert verified is None

    asyncio.run(exercise_verifier())


# ─── FastMCP transport ────────────────────────────────────────────────────────


@asynccontextmanager
async def _mcp_client(
    token: str | None, *, response_bodies: list[bytes] | None = None
) -> AsyncIterator[Client[Any]]:
    from news_dashboard.mcp.server import mcp_http_app

    async def capture_responses(scope: Scope, receive: Receive, send: Send) -> None:
        body_parts: list[bytes] = []

        async def capture_send(message: Message) -> None:
            if message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))
                if not message.get("more_body", False) and response_bodies is not None:
                    response_bodies.append(b"".join(body_parts))
            await send(message)

        await mcp_http_app(scope, receive, capture_send)

    transport_app = Starlette(
        routes=[Mount("/mcp", app=capture_responses)],
        lifespan=mcp_http_app.lifespan,
    )

    def httpx_client_factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
        *,
        follow_redirects: bool = True,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=transport_app),
            base_url="http://mcp.test",
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=follow_redirects,
        )

    transport = StreamableHttpTransport(
        "http://mcp.test/mcp/",
        auth=token,
        httpx_client_factory=httpx_client_factory,
    )
    client_error: BaseException | None = None
    async with transport_app.router.lifespan_context(transport_app):
        try:
            async with Client(transport) as mcp_client:
                yield mcp_client
        except BaseException as exc:
            client_error = exc
    if client_error is not None:
        raise client_error


def test_fastmcp_initializes_and_lists_only_latest_news_tool(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    user_id = _make_user(pg_clean, "alice-fastmcp-list")
    created = service.create_token(user_id, "client", scopes=("search",), database_url=pg_clean)

    async def exercise() -> None:
        async with _mcp_client(created["token"]) as mcp_client:
            tools = await mcp_client.list_tools()
        assert [tool.name for tool in tools] == ["list_latest_news"]

    asyncio.run(exercise())


def test_latest_news_returns_compact_articles_visible_to_token_owner(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-fastmcp-news")
    _seed_source(pg_clean)
    _seed_article(pg_clean, 1)
    created = service.create_token(alice, "client", scopes=("search",), database_url=pg_clean)

    async def exercise() -> None:
        async with _mcp_client(created["token"]) as mcp_client:
            result = await mcp_client.call_tool("list_latest_news", {"limit": 10})
        assert result.structured_content is not None
        articles = result.structured_content["articles"]
        assert len(articles) == 1
        article = articles[0]
        discovered_at = article.pop("discovered_at")
        assert isinstance(discovered_at, str)
        assert article == {
            "id": 1,
            "title": "Article 1",
            "url": "https://example.com/1",
            "source_slug": "test-source",
            "source_name": "test-source",
            "category": "engineering",
            "published_at": None,
            "summary": "Summary 1",
            "state": "today",
        }

    asyncio.run(exercise())


def test_latest_news_isolates_private_sources_by_token_owner(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-private-mcp")
    bob = _make_user(pg_clean, "bob-private-mcp")
    _seed_source(pg_clean, "alice-private", owner_user_id=alice)
    _seed_article(pg_clean, 42, source_slug="alice-private")
    alice_token = service.create_token(alice, "client", scopes=("search",), database_url=pg_clean)
    bob_token = service.create_token(bob, "client", scopes=("search",), database_url=pg_clean)

    async def article_ids(token: str) -> list[int]:
        async with _mcp_client(token) as mcp_client:
            result = await mcp_client.call_tool("list_latest_news")
        assert result.structured_content is not None
        return [article["id"] for article in result.structured_content["articles"]]

    assert asyncio.run(article_ids(alice_token["token"])) == [42]
    assert asyncio.run(article_ids(bob_token["token"])) == []


def test_latest_news_requires_search_scope(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    user_id = _make_user(pg_clean, "alice-fastmcp-scope")
    created = service.create_token(user_id, "client", scopes=("read",), database_url=pg_clean)

    async def exercise() -> None:
        async with _mcp_client(created["token"]) as mcp_client:
            assert await mcp_client.list_tools() == []
            result = await mcp_client.call_tool("list_latest_news", raise_on_error=False)
        assert result.is_error is True

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "arguments",
    [
        {"date_range": "year"},
        {"sources": [f"source-{index}" for index in range(51)]},
    ],
)
def test_latest_news_rejects_invalid_or_unbounded_filters(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
    arguments: dict[str, Any],
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    user_id = _make_user(pg_clean, f"alice-invalid-{len(arguments)}")
    created = service.create_token(user_id, "client", scopes=("search",), database_url=pg_clean)

    async def exercise() -> None:
        async with _mcp_client(created["token"]) as mcp_client:
            result = await mcp_client.call_tool("list_latest_news", arguments, raise_on_error=False)
        assert result.is_error is True

    asyncio.run(exercise())


def test_latest_news_clamps_limit_to_twenty_five(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    user_id = _make_user(pg_clean, "alice-fastmcp-limit")
    _seed_source(pg_clean)
    for article_id in range(1, 31):
        _seed_article(pg_clean, article_id)
    created = service.create_token(user_id, "client", scopes=("search",), database_url=pg_clean)

    async def exercise() -> None:
        async with _mcp_client(created["token"]) as mcp_client:
            result = await mcp_client.call_tool("list_latest_news", {"limit": 10_000})
        assert result.structured_content is not None
        assert 0 < len(result.structured_content["articles"]) <= 25
        assert result.structured_content["truncated"] is True

    asyncio.run(exercise())


def test_fastmcp_rate_limits_each_non_secret_token_identity(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    first_user = _make_user(pg_clean, "alice-fastmcp-rate")
    second_user = _make_user(pg_clean, "bob-fastmcp-rate")
    first = service.create_token(
        first_user, "first-client", scopes=("search",), database_url=pg_clean
    )
    second = service.create_token(
        second_user, "second-client", scopes=("search",), database_url=pg_clean
    )

    async def exercise() -> None:
        async with _mcp_client(first["token"]) as first_client:
            results = [
                await first_client.call_tool("list_latest_news", raise_on_error=False)
                for _ in range(15)
            ]
        limited = next(result for result in results if result.is_error)
        limited_text = " ".join(
            block.text for block in limited.content if isinstance(block, TextContent)
        )
        assert "Internal server error" in limited_text
        assert first["token"] not in limited_text

        async with _mcp_client(second["token"]) as second_client:
            result = await second_client.call_tool("list_latest_news", raise_on_error=False)
        assert result.is_error is False

    asyncio.run(exercise())


def test_fastmcp_rate_limiter_evicts_old_inactive_identities() -> None:
    from news_dashboard.mcp.server import _BoundedTokenBuckets

    buckets = _BoundedTokenBuckets(max_identities=3, capacity=2, refill_rate=1.0)
    first = buckets.for_client("mcp-token:1")
    buckets.for_client("mcp-token:2")
    buckets.for_client("mcp-token:3")
    buckets.for_client("mcp-token:4")

    assert len(buckets) == 3
    assert buckets.for_client("mcp-token:1") is not first


def test_fastmcp_bounds_oversized_tool_output(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import server, service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    user_id = _make_user(pg_clean, "alice-fastmcp-response-limit")
    created = service.create_token(user_id, "client", scopes=("search",), database_url=pg_clean)
    adversarial_text = '\\"雪🙂' * 20_000
    monkeypatch.setattr(
        server,
        "search_articles",
        lambda **_kwargs: [
            {
                "id": 99,
                "title": adversarial_text,
                "url": f"https://example.com/{adversarial_text}",
                "source_slug": adversarial_text,
                "source_name": adversarial_text,
                "category": adversarial_text,
                "published_at": None,
                "discovered_at": None,
                "summary": adversarial_text,
                "state": "today",
            }
        ],
    )
    response_bodies: list[bytes] = []

    async def exercise() -> None:
        async with _mcp_client(created["token"], response_bodies=response_bodies) as mcp_client:
            result = await mcp_client.call_tool("list_latest_news")
        assert result.structured_content is not None
        assert result.structured_content["truncated"] is True
        assert len(result.structured_content["articles"]) == 0

    asyncio.run(exercise())

    tool_response = next(
        body
        for body in response_bodies
        if b'"structuredContent"' in body and b'"truncated":true' in body
    )
    assert len(tool_response) <= 16_384
    json.loads(tool_response.split(b"data: ", 1)[1].splitlines()[0])


def test_fastmcp_invalid_arguments_never_leak_to_response_or_logs(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    user_id = _make_user(pg_clean, "alice-fastmcp-invalid-secret")
    created = service.create_token(user_id, "client", scopes=("search",), database_url=pg_clean)
    rejected_argument = "rejected-private-value-9c2"
    caplog.set_level(logging.WARNING)

    async def exercise() -> None:
        async with _mcp_client(created["token"]) as mcp_client:
            result = await mcp_client.call_tool(
                "list_latest_news",
                {"date_range": rejected_argument},
                raise_on_error=False,
            )
        rendered = " ".join(
            block.text for block in result.content if isinstance(block, TextContent)
        )
        assert result.is_error is True
        assert rejected_argument not in rendered

    asyncio.run(exercise())
    assert rejected_argument not in caplog.text


def test_fastmcp_sanitizes_internal_errors_and_logs_metadata_only(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from news_dashboard.mcp import server, service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    user_id = _make_user(pg_clean, "alice-fastmcp-sanitize")
    created = service.create_token(user_id, "client", scopes=("search",), database_url=pg_clean)
    bearer_token = created["token"]
    private_argument = "secret-source-filter"
    internal_detail = "password=provider-secret db=postgresql://internal"

    def fail_search(**_kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError(internal_detail)

    monkeypatch.setattr(server, "search_articles", fail_search)
    caplog.set_level(logging.INFO, logger="news_dashboard.mcp")

    async def exercise() -> None:
        async with _mcp_client(bearer_token) as mcp_client:
            result = await mcp_client.call_tool(
                "list_latest_news",
                {"sources": [private_argument]},
                raise_on_error=False,
            )
        rendered = " ".join(
            block.text for block in result.content if isinstance(block, TextContent)
        )
        assert result.is_error is True
        assert "Internal server error" in rendered
        assert internal_detail not in rendered
        assert "Traceback" not in rendered

    asyncio.run(exercise())

    logs = caplog.text
    assert "tool=list_latest_news" in logs
    assert "status=error" in logs
    assert "duration_ms=" in logs
    for sensitive_value in (
        bearer_token,
        private_argument,
        internal_detail,
        "provider-secret",
    ):
        assert sensitive_value not in logs


@pytest.mark.parametrize("mode", ["revoked", "unauthenticated", "disabled"])
def test_fastmcp_transport_rejects_unavailable_authentication(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    user_id = _make_user(pg_clean, f"alice-fastmcp-{mode}")
    created = service.create_token(user_id, "client", scopes=("search",), database_url=pg_clean)
    token: str | None = created["token"]
    if mode == "revoked":
        service.revoke_token(user_id, created["id"], database_url=pg_clean)
    elif mode == "unauthenticated":
        token = None
    else:
        monkeypatch.setenv("MCP_SERVER_ENABLED", "false")

    async def exercise() -> None:
        expected_exception = McpError if mode == "disabled" else httpx.HTTPStatusError
        with pytest.raises(expected_exception) as exc_info:
            async with _mcp_client(token):
                pass
        if isinstance(exc_info.value, httpx.HTTPStatusError):
            assert exc_info.value.response.status_code == 401

    asyncio.run(exercise())


# ─── HTTP token-management endpoints ─────────────────────────────────────────


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _client_for(user_id: int) -> TestClient:
    from news_dashboard.auth import require_auth

    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    return TestClient(app, raise_server_exceptions=True)


def test_token_management_endpoint_rejects_when_mcp_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_SERVER_ENABLED", "false")
    resp = client.post("/api/users/me/mcp-tokens", json={"name": "client"})
    assert resp.status_code == 403


def test_token_management_endpoints_when_enabled(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-http")

    with _client_for(alice) as client:
        created = client.post("/api/users/me/mcp-tokens", json={"name": "Claude Desktop"})
        assert created.status_code == 200
        body = created.json()
        assert body["token"].startswith("ndmcp_")
        assert sorted(body["scopes"]) == sorted(["search", "read", "ask", "briefings"])
        token_id = body["id"]

        listed = client.get("/api/users/me/mcp-tokens")
        assert listed.status_code == 200
        assert listed.json()["enabled"] is True
        assert len(listed.json()["items"]) == 1
        assert "token" not in listed.json()["items"][0]

        revoked = client.delete(f"/api/users/me/mcp-tokens/{token_id}")
        assert revoked.status_code == 200
        assert revoked.json()["revoked_at"] is not None


def test_create_token_with_explicit_scope_subset(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-scopes")

    with _client_for(alice) as client:
        created = client.post(
            "/api/users/me/mcp-tokens",
            json={"name": "search-only", "scopes": ["search"]},
        )
        assert created.status_code == 200
        assert created.json()["scopes"] == ["search"]


def test_create_token_rejects_unknown_scope(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-badscope")

    with _client_for(alice) as client:
        resp = client.post(
            "/api/users/me/mcp-tokens",
            json={"name": "client", "scopes": ["search", "delete_everything"]},
        )
        assert resp.status_code == 422


def test_create_token_rejects_empty_scope_list(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-emptyscope")

    with _client_for(alice) as client:
        resp = client.post(
            "/api/users/me/mcp-tokens",
            json={"name": "client", "scopes": []},
        )
        assert resp.status_code == 422


def test_legacy_mcp_endpoints_no_longer_exist(client: TestClient) -> None:
    assert client.get("/api/mcp/tools").status_code == 404
    assert client.post("/api/mcp/rpc", json={}).status_code in {404, 405}
