"""Tests for the A2A (Agent2Agent) protocol endpoint.

The server must be usable by any standard A2A client, so the round-trip test
drives it with the official ``a2a-sdk`` client over an ASGI transport.
"""

from __future__ import annotations

import asyncio
from typing import Any

import a2a.types as a2a_types
import httpx
import pytest
from fastapi.testclient import TestClient
from google.protobuf.json_format import ParseDict

from news_dashboard.db import connect
from news_dashboard.main import app

RPC_PATH = "/api/a2a"
CARD_PATH = "/.well-known/agent-card.json"


def _make_user(database_url: str, username: str) -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'hash') RETURNING id",
            (username,),
        ).fetchone()
    return int(row["id"])


def _make_token(database_url: str, user_id: int, scopes: tuple[str, ...] = ("ask",)) -> str:
    from news_dashboard.mcp import service as mcp_service

    created = mcp_service.create_token(
        user_id, "a2a-test-client", scopes=scopes, database_url=database_url
    )
    return str(created["token"])


def _rpc_payload(text: str = "what is new?") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": "msg-1",
                "role": "ROLE_USER",
                "parts": [{"text": text}],
            }
        },
    }


def _post_rpc(headers: dict[str, str] | None = None, text: str = "what is new?") -> httpx.Response:
    with TestClient(app, raise_server_exceptions=False) as client:
        resp: httpx.Response = client.post(RPC_PATH, json=_rpc_payload(text), headers=headers or {})
    return resp


# ─── service.py — enablement ─────────────────────────────────────────────────


def test_a2a_enabled_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.a2a import service

    monkeypatch.delenv("A2A_SERVER_ENABLED", raising=False)
    assert service.a2a_enabled() is False

    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    assert service.a2a_enabled() is True

    monkeypatch.setenv("A2A_SERVER_ENABLED", "0")
    assert service.a2a_enabled() is False


# ─── agent card ──────────────────────────────────────────────────────────────


def test_agent_card_requires_a2a_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A2A_SERVER_ENABLED", raising=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(CARD_PATH)
    assert resp.status_code == 403


def test_agent_card_is_spec_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    # APP_BASE_URL is the highest-precedence base-URL variable (the one standard
    # deployments set), so the card must honor it.
    monkeypatch.setenv("APP_BASE_URL", "http://testserver")
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(CARD_PATH)
    assert resp.status_code == 200

    body = resp.json()
    # The card must parse into the official protobuf AgentCard type. The extra
    # top-level fields are the SDK's 0.3 backward-compat card shape.
    card = ParseDict(body, a2a_types.AgentCard(), ignore_unknown_fields=True)
    assert card.name
    assert card.description
    versions = {i.protocol_version for i in card.supported_interfaces}
    assert "1.0" in versions
    assert "0.3" in versions  # matches the endpoint's enable_v0_3_compat
    assert all(i.url == f"http://testserver{RPC_PATH}" for i in card.supported_interfaces)
    # 0.3 clients discover via the compat top-level url field.
    assert body["url"] == f"http://testserver{RPC_PATH}"
    assert card.capabilities.streaming is False
    assert card.capabilities.push_notifications is False
    # Exactly one read-only Q&A skill.
    assert len(card.skills) == 1
    assert card.skills[0].id == "ask_news"
    assert "Starred + Done" in card.description
    assert "Starred + Done" in card.skills[0].description
    # Bearer auth must be declared.
    schemes = dict(card.security_schemes)
    assert any(s.WhichOneof("scheme") == "http_auth_security_scheme" for s in schemes.values())


# ─── JSON-RPC auth ───────────────────────────────────────────────────────────


def test_rpc_requires_a2a_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A2A_SERVER_ENABLED", raising=False)
    assert _post_rpc().status_code == 403


def test_rpc_rejects_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    assert _post_rpc().status_code == 401


def test_rpc_rejects_invalid_token(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    resp = _post_rpc(headers={"Authorization": "Bearer ndmcp_not-a-real-token"})
    assert resp.status_code == 401


def test_rpc_rejects_revoked_token(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.mcp import service as mcp_service

    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-a2a-revoked")
    created = mcp_service.create_token(alice, "revoked", scopes=("ask",), database_url=pg_clean)
    mcp_service.revoke_token(alice, int(created["id"]), database_url=pg_clean)

    resp = _post_rpc(headers={"Authorization": f"Bearer {created['token']}"})
    assert resp.status_code == 401


def test_rpc_rejects_token_without_ask_scope(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-a2a-noscope")
    token = _make_token(pg_clean, alice, scopes=("search",))

    resp = _post_rpc(headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# ─── SendMessage behavior ────────────────────────────────────────────────────


def _stub_ask(monkeypatch: pytest.MonkeyPatch, answer: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_ask(
        query: str,
        *,
        include_all: bool,
        user_id: int,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        calls.append({"query": query, "include_all": include_all, "user_id": user_id})
        return {
            "answer": answer,
            "sources": [{"id": 1, "title": "Article 1", "url": "https://example.com/1"}],
        }

    monkeypatch.setattr("news_dashboard.assistant.service.ask", fake_ask)
    return calls


def test_send_message_roundtrip_with_official_client(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from a2a.client import ClientConfig, create_client
    from a2a.helpers import get_message_text

    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    monkeypatch.setenv("APP_BASE_URL", "http://testserver")
    alice = _make_user(pg_clean, "alice-a2a-roundtrip")
    token = _make_token(pg_clean, alice)
    calls = _stub_ask(monkeypatch, answer="the corpus answer")

    async def run() -> str:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as http_client:
            card_resp = await http_client.get(CARD_PATH)
            card = ParseDict(card_resp.json(), a2a_types.AgentCard(), ignore_unknown_fields=True)
            client = await create_client(
                card, ClientConfig(streaming=False, httpx_client=http_client)
            )
            request = a2a_types.SendMessageRequest(
                message=a2a_types.Message(
                    message_id="msg-roundtrip",
                    role=a2a_types.Role.ROLE_USER,
                    parts=[a2a_types.Part(text="what happened this week?")],
                )
            )
            texts = [
                get_message_text(response.message)
                async for response in client.send_message(request)
                if response.HasField("message")
            ]
            return "\n".join(texts)

    text = asyncio.run(run())
    assert "the corpus answer" in text
    assert calls == [{"query": "what happened this week?", "include_all": False, "user_id": alice}]


def test_send_message_answers_as_agent_message(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-a2a-raw")
    token = _make_token(pg_clean, alice)
    _stub_ask(monkeypatch, answer="raw rpc answer")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            RPC_PATH,
            json=_rpc_payload("anything new?"),
            headers={"Authorization": f"Bearer {token}", "A2A-Version": "1.0"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body
    message = body["result"]["message"]
    assert message["role"] == "ROLE_AGENT"
    assert any("raw rpc answer" in part.get("text", "") for part in message["parts"])


def test_send_message_rejects_overlong_query(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from news_dashboard.mcp.models import MAX_QUERY_LENGTH

    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-a2a-bounds")
    token = _make_token(pg_clean, alice)
    calls = _stub_ask(monkeypatch, answer="never returned")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            RPC_PATH,
            json=_rpc_payload("x" * (MAX_QUERY_LENGTH + 1)),
            headers={"Authorization": f"Bearer {token}", "A2A-Version": "1.0"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert calls == []


def test_send_message_maps_embedding_outage_to_rpc_error(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An embedding outage must surface as a JSON-RPC error, not an HTTP 500."""
    from news_dashboard.embeddings import EmbeddingUnavailableError

    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-a2a-outage")
    token = _make_token(pg_clean, alice)

    def broken_ask(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise EmbeddingUnavailableError

    monkeypatch.setattr("news_dashboard.assistant.service.ask", broken_ask)

    resp = _post_rpc(headers={"Authorization": f"Bearer {token}", "A2A-Version": "1.0"})
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body
    assert "unavailable" in body["error"]["message"].lower()


def test_send_message_accepts_v03_style_request(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Older 0.3 clients (kind discriminators, kebab-case enums) must still work."""
    monkeypatch.setenv("A2A_SERVER_ENABLED", "true")
    alice = _make_user(pg_clean, "alice-a2a-v03")
    token = _make_token(pg_clean, alice)
    _stub_ask(monkeypatch, answer="v03 answer")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": "msg-v03",
                "role": "user",
                "parts": [{"kind": "text", "text": "hello from an old client"}],
            }
        },
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            RPC_PATH,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body
