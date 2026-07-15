from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from news_dashboard.db import connect
from news_dashboard.main import app


def _make_user(database_url: str, username: str) -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'hash') RETURNING id",
            (username,),
        ).fetchone()
    return int(row["id"])


def _seed_source(database_url: str, slug: str = "test-source") -> None:
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, 'engineering', 'rss', 50, TRUE)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug, f"https://example.com/{slug}.xml"),
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


def _insert_briefing(database_url: str, user_id: int) -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(scope, status, title, summary, user_id)
            VALUES ('since_last_briefing', 'complete', 'Test Brief', 'Summary', %s)
            RETURNING id
            """,
            (user_id,),
        ).fetchone()
    return int(row["id"])


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


def test_mcp_enabled_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.mcp import service

    monkeypatch.delenv("MCP_SERVER_ENABLED", raising=False)
    assert service.mcp_enabled() is False

    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    assert service.mcp_enabled() is True

    monkeypatch.setenv("MCP_SERVER_ENABLED", "0")
    assert service.mcp_enabled() is False


# ─── tools.py — scope checks and result bounds ───────────────────────────────


def test_call_tool_rejects_unknown_tool(pg_clean: str) -> None:
    from news_dashboard.mcp.tools import ToolError, call_tool

    alice = _make_user(pg_clean, "alice-tool")
    with pytest.raises(ToolError) as exc_info:
        call_tool("delete_everything", {}, user_id=alice, scopes={"search", "read", "ask"})
    assert exc_info.value.status_code == 404


def test_call_tool_enforces_scope(pg_clean: str) -> None:
    from news_dashboard.mcp.tools import ToolError, call_tool

    alice = _make_user(pg_clean, "alice-scope")
    with pytest.raises(ToolError) as exc_info:
        call_tool("search_articles", {"q": ""}, user_id=alice, scopes=set())
    assert exc_info.value.status_code == 403


def test_search_articles_tool_is_scoped_per_user(pg_clean: str) -> None:
    from news_dashboard.mcp.tools import call_tool

    _seed_source(pg_clean)
    alice = _make_user(pg_clean, "alice-search")
    bob = _make_user(pg_clean, "bob-search")
    _seed_article(pg_clean, 1)

    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (%s, %s, %s)",
            (bob, "test-source", False),
        )

    alice_result = call_tool("search_articles", {"limit": 100}, user_id=alice, scopes={"search"})
    bob_result = call_tool("search_articles", {"limit": 100}, user_id=bob, scopes={"search"})

    assert any(a["id"] == 1 for a in alice_result["articles"])
    assert not any(a["id"] == 1 for a in bob_result["articles"])


def test_search_articles_tool_clamps_limit(pg_clean: str) -> None:
    from news_dashboard.mcp.models import MAX_RESULT_LIMIT
    from news_dashboard.mcp.tools import call_tool

    _seed_source(pg_clean)
    alice = _make_user(pg_clean, "alice-clamp")

    result = call_tool("search_articles", {"limit": 999999}, user_id=alice, scopes={"search"})
    assert len(result["articles"]) <= MAX_RESULT_LIMIT


def test_get_article_tool_denies_invisible_article(pg_clean: str) -> None:
    from news_dashboard.mcp.tools import ToolError, call_tool

    _seed_source(pg_clean, "private-source")
    alice = _make_user(pg_clean, "alice-owner")
    bob = _make_user(pg_clean, "bob-visitor")
    _seed_article(pg_clean, 42, source_slug="private-source")

    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "UPDATE sources SET owner_user_id = %s, enabled = TRUE WHERE slug = %s",
            (alice, "private-source"),
        )

    owner_result = call_tool("get_article", {"article_id": 42}, user_id=alice, scopes={"read"})
    assert owner_result["article"]["id"] == 42

    with pytest.raises(ToolError) as exc_info:
        call_tool("get_article", {"article_id": 42}, user_id=bob, scopes={"read"})
    assert exc_info.value.status_code == 404


def test_list_briefings_tool_is_scoped_per_user(pg_clean: str) -> None:
    from news_dashboard.mcp.tools import call_tool

    alice = _make_user(pg_clean, "alice-brief")
    bob = _make_user(pg_clean, "bob-brief")
    _insert_briefing(pg_clean, alice)

    alice_result = call_tool("list_briefings", {}, user_id=alice, scopes={"briefings"})
    bob_result = call_tool("list_briefings", {}, user_id=bob, scopes={"briefings"})

    assert len(alice_result["briefings"]) == 1
    assert bob_result["briefings"] == []


def _pack(vector: list[float]) -> str:
    """A pgvector literal padded to the real embedding_vec(1536) width."""
    from news_dashboard.db import EMBEDDING_DIMENSIONS
    from news_dashboard.embeddings import vector_literal

    return vector_literal(vector + [0.0] * (EMBEDDING_DIMENSIONS - len(vector)))


def _make_openai_stub(monkeypatch: pytest.MonkeyPatch, answer: str = "ok") -> None:
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    class FakeEmbeddingData:
        def __init__(self) -> None:
            from news_dashboard.db import EMBEDDING_DIMENSIONS

            self.embedding = [0.1] * 10 + [0.0] * (EMBEDDING_DIMENSIONS - 10)

    class FakeEmbeddingResponse:
        def __init__(self) -> None:
            self.data = [FakeEmbeddingData()]

    class FakeEmbeddings:
        def create(self, **_: Any) -> FakeEmbeddingResponse:
            return FakeEmbeddingResponse()

    class FakeOpenAI:
        def __init__(self, **_: object) -> None:
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr("news_dashboard.ai_client.get_openai_client", FakeOpenAI)
    monkeypatch.setattr(
        "news_dashboard.ai_client.get_chat_model",
        lambda **_kwargs: RunnableLambda(lambda _value: AIMessage(content=answer)),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def test_ask_tool_rejects_empty_query(pg_clean: str) -> None:
    from news_dashboard.mcp.tools import ToolError, call_tool

    alice = _make_user(pg_clean, "alice-ask-empty")
    with pytest.raises(ToolError):
        call_tool("ask", {"query": "   "}, user_id=alice, scopes={"ask"})


def test_ask_tool_answers_over_users_corpus(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.mcp.tools import call_tool

    _seed_source(pg_clean)
    alice = _make_user(pg_clean, "alice-ask")
    embedding = _pack([0.1] * 10)
    with connect(database_url=pg_clean) as conn:
        for i in range(1, 6):
            conn.execute(
                """
                INSERT INTO articles(
                    id, url, canonical_url, title, source_slug, source_name,
                    category, kind, status, importance_score, summary, reason,
                    tags, embedding_vec
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    i,
                    f"https://example.com/{i}",
                    f"https://example.com/{i}",
                    f"Article {i}",
                    "test-source",
                    "test-source",
                    "engineering",
                    "rss",
                    "saved",
                    0.5,
                    f"Summary {i}",
                    "",
                    "",
                    embedding,
                ),
            )
            conn.execute(
                "INSERT INTO user_article_state(user_id, article_id, state)"
                " VALUES (%s, %s, 'done')",
                (alice, i),
            )

    _make_openai_stub(monkeypatch, answer="corpus answer")
    result = call_tool("ask", {"query": "what's new?"}, user_id=alice, scopes={"ask"})
    assert result["answer"] == "corpus answer"


# ─── HTTP endpoints ───────────────────────────────────────────────────────────


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


def test_token_management_endpoints_require_mcp_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MCP_SERVER_ENABLED", raising=False)
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


def test_rpc_endpoint_rejects_missing_or_invalid_bearer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")

    resp = client.post("/api/mcp/rpc", json={"tool": "search_articles", "arguments": {}})
    assert resp.status_code == 401

    resp = client.post(
        "/api/mcp/rpc",
        json={"tool": "search_articles", "arguments": {}},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_rpc_endpoint_disabled_by_default(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MCP_SERVER_ENABLED", raising=False)
    resp = client.post(
        "/api/mcp/rpc",
        json={"tool": "search_articles", "arguments": {}},
        headers={"Authorization": "Bearer ndmcp_whatever"},
    )
    assert resp.status_code == 403


def test_rpc_endpoint_calls_tool_with_valid_token(
    client: TestClient, pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    _seed_source(pg_clean)
    alice = _make_user(pg_clean, "alice-rpc")
    _seed_article(pg_clean, 7)
    created = service.create_token(alice, "client", database_url=pg_clean)

    resp = client.post(
        "/api/mcp/rpc",
        json={"tool": "search_articles", "arguments": {"limit": 10}},
        headers={"Authorization": f"Bearer {created['token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "search_articles"
    assert any(a["id"] == 7 for a in body["result"]["articles"])


def test_rpc_endpoint_denies_tool_outside_token_scopes(
    client: TestClient, pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-scoped-rpc")
    created = service.create_token(alice, "search-only", scopes=("search",), database_url=pg_clean)

    ok = client.post(
        "/api/mcp/rpc",
        json={"tool": "search_articles", "arguments": {}},
        headers={"Authorization": f"Bearer {created['token']}"},
    )
    assert ok.status_code == 200

    denied = client.post(
        "/api/mcp/rpc",
        json={"tool": "list_briefings", "arguments": {}},
        headers={"Authorization": f"Bearer {created['token']}"},
    )
    assert denied.status_code == 403


def test_rpc_endpoint_lists_tools(
    client: TestClient, pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-listtools")
    created = service.create_token(alice, "client", database_url=pg_clean)

    resp = client.get("/api/mcp/tools", headers={"Authorization": f"Bearer {created['token']}"})
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["tools"]}
    assert {"search_articles", "get_article", "list_briefings", "ask"} <= names
