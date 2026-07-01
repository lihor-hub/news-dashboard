"""Tests for #101: persist and read saved briefings — API layer.

Strategy:
- Schema tests inspect the PostgreSQL DDL constants for the saved briefing tables.
- API-contract tests: use FastAPI's TestClient and monkeypatch the imported
  names in news_dashboard.main (the module that actually calls them) so no
  PostgreSQL connection is required.  Patching the *importer's* namespace is
  the standard Python pattern for ``from module import name`` style imports.

See test_briefings_db.py for PostgreSQL integration tests that exercise the
actual psycopg %s parameterisation, JSONB round-trip, and NULLS LAST ordering.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import news_dashboard.main as main_mod
from news_dashboard.briefings import (
    BriefingAINotConfiguredError,
    BriefingGenerationError,
    BriefingNotFoundError,
)
from news_dashboard.db import POSTGRES_SCHEMA
from news_dashboard.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── Test fixtures ─────────────────────────────────────────────────────────────

_SAMPLE_ARTICLE = {
    "id": 42,
    "title": "Claude 4 Released",
    "url": "https://example.com/claude-4",
    "canonical_url": "https://example.com/claude-4",
    "source_name": "Anthropic Blog",
    "category": "ai",
    "kind": "rss_feed",
    "published_at": "2026-06-13T10:00:00+00:00",
    "summary": "Anthropic releases Claude 4 with improved reasoning.",
    "importance_score": 90,
    "section_index": 0,
    "citation_index": 0,
}

_SAMPLE_BRIEFING = {
    "id": 1,
    "created_at": "2026-06-13T12:00:00+00:00",
    "scope": "since_last_briefing",
    "since_at": "2026-06-12T12:00:00+00:00",
    "until_at": "2026-06-13T12:00:00+00:00",
    "status": "complete",
    "title": "AI Frameworks Tighten Production Workflows",
    "summary": "New agent frameworks and observability tools toward production-grade AI.",
    "content": {
        "sections": [
            {
                "title": "Agent frameworks",
                "body": "LangGraph and related updates.",
                "citations": [42],
            }
        ],
        "worth_opening": [42],
    },
    "model": "claude-sonnet-4-6",
    "error": None,
    "articles": [_SAMPLE_ARTICLE],
}

_SAMPLE_LIST_ITEM = {
    "id": 1,
    "created_at": "2026-06-13T12:00:00+00:00",
    "scope": "since_last_briefing",
    "since_at": "2026-06-12T12:00:00+00:00",
    "until_at": "2026-06-13T12:00:00+00:00",
    "status": "complete",
    "title": "AI Frameworks Tighten Production Workflows",
    "summary": "New agent frameworks and observability tools.",
    "model": "claude-sonnet-4-6",
    "error": None,
}


# ── Table initialisation ──────────────────────────────────────────────────────


def test_schema_creates_briefings_table() -> None:
    schema = "\n".join(POSTGRES_SCHEMA).lower()
    assert "create table if not exists briefings" in schema


def test_schema_creates_briefing_articles_table() -> None:
    schema = "\n".join(POSTGRES_SCHEMA).lower()
    assert "create table if not exists briefing_articles" in schema


def test_briefings_table_columns() -> None:
    schema = "\n".join(POSTGRES_SCHEMA).lower()
    for column in ("id", "created_at", "scope", "since_at", "until_at", "content"):
        assert column in schema


def test_briefing_articles_table_columns() -> None:
    schema = "\n".join(POSTGRES_SCHEMA).lower()
    for column in ("briefing_id", "article_id", "section_index", "citation_index"):
        assert column in schema


# ── GET /api/briefings/latest — empty state ───────────────────────────────────


def test_latest_empty_state_when_no_briefing(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_latest_briefing", lambda **_: None)
    resp = client.get("/api/briefings/latest")
    assert resp.status_code == 200
    assert resp.json() == {"status": "empty"}


# ── GET /api/briefings/latest — with a saved briefing ────────────────────────


def test_latest_returns_briefing_metadata(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_latest_briefing", lambda **_: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert data["title"] == "AI Frameworks Tighten Production Workflows"
    assert data["status"] == "complete"


def test_latest_returns_structured_content(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_latest_briefing", lambda **_: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/latest")
    data = resp.json()
    assert "content" in data
    assert "sections" in data["content"]
    assert len(data["content"]["sections"]) == 1
    assert data["content"]["worth_opening"] == [42]


def test_latest_returns_cited_article_metadata(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_latest_briefing", lambda **_: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/latest")
    data = resp.json()
    assert "articles" in data
    assert len(data["articles"]) == 1
    article = data["articles"][0]
    assert article["id"] == 42
    assert article["title"] == "Claude 4 Released"
    assert article["source_name"] == "Anthropic Blog"
    assert article["section_index"] == 0
    assert article["citation_index"] == 0


# ── GET /api/briefings — history list ────────────────────────────────────────


def test_list_returns_items_key(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "list_briefings", lambda **_: [dict(_SAMPLE_LIST_ITEM)])
    resp = client.get("/api/briefings")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == 1


def test_list_empty_when_no_briefings(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "list_briefings", lambda **_: [])
    resp = client.get("/api/briefings")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_list_items_omit_content_blob(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "list_briefings", lambda **_: [dict(_SAMPLE_LIST_ITEM)])
    resp = client.get("/api/briefings")
    item = resp.json()["items"][0]
    assert "content" not in item
    assert "articles" not in item


def test_list_respects_limit_and_offset_params(client: TestClient, monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def _mock(**kw: Any) -> list[dict[str, Any]]:
        captured.update(kw)
        return []

    monkeypatch.setattr(main_mod, "list_briefings", _mock)
    client.get("/api/briefings?limit=10&offset=20")
    assert captured.get("limit") == 10
    assert captured.get("offset") == 20


# ── GET /api/briefings/{id} — detail ─────────────────────────────────────────


def test_detail_returns_full_briefing_with_articles(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert "content" in data
    assert len(data["articles"]) == 1


def test_detail_404_for_missing_briefing(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: None)
    resp = client.get("/api/briefings/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "briefing not found"


def test_detail_passes_id_to_backend(client: TestClient, monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def _mock(bid: int, **_: Any) -> dict[str, Any] | None:
        captured["bid"] = bid
        return dict(_SAMPLE_BRIEFING)

    monkeypatch.setattr(main_mod, "get_briefing", _mock)
    client.get("/api/briefings/7")
    assert captured["bid"] == 7


def test_detail_returns_scope_and_time_window(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/1")
    data = resp.json()
    assert data["scope"] == "since_last_briefing"
    assert data["since_at"] is not None
    assert data["until_at"] is not None


def test_detail_cited_article_has_section_and_citation_index(
    client: TestClient, monkeypatch: Any
) -> None:
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/1")
    article = resp.json()["articles"][0]
    assert "section_index" in article
    assert "citation_index" in article


# ── POST /api/briefings — generate ───────────────────────────────────────────


def test_create_returns_briefing_on_success(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "generate_briefing", lambda **_: dict(_SAMPLE_BRIEFING))
    resp = client.post("/api/briefings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert data["status"] == "complete"
    assert "articles" in data


def test_create_returns_no_candidates_when_no_today_articles(
    client: TestClient, monkeypatch: Any
) -> None:
    monkeypatch.setattr(main_mod, "generate_briefing", lambda **_: {"status": "no_candidates"})
    resp = client.post("/api/briefings")
    assert resp.status_code == 200
    assert resp.json() == {"status": "no_candidates"}


def test_create_returns_503_when_ai_not_configured(client: TestClient, monkeypatch: Any) -> None:
    def _raise(**_: Any) -> dict[str, Any]:
        msg = "OPENAI_API_KEY not set"
        raise BriefingAINotConfiguredError(msg)

    monkeypatch.setattr(main_mod, "generate_briefing", _raise)
    resp = client.post("/api/briefings")
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]


def test_create_returns_500_when_generation_fails(client: TestClient, monkeypatch: Any) -> None:
    def _raise(**_: Any) -> dict[str, Any]:
        msg = "AI returned invalid JSON"
        raise BriefingGenerationError(msg)

    monkeypatch.setattr(main_mod, "generate_briefing", _raise)
    resp = client.post("/api/briefings")
    assert resp.status_code == 500
    assert "invalid JSON" in resp.json()["detail"]


def test_create_returns_content_and_articles_on_success(
    client: TestClient, monkeypatch: Any
) -> None:
    monkeypatch.setattr(main_mod, "generate_briefing", lambda **_: dict(_SAMPLE_BRIEFING))
    resp = client.post("/api/briefings")
    data = resp.json()
    assert "content" in data
    assert "sections" in data["content"]
    assert "articles" in data
    assert len(data["articles"]) > 0


def test_create_returns_existing_briefing_inside_idempotency_window(
    client: TestClient, monkeypatch: Any
) -> None:
    existing = dict(_SAMPLE_BRIEFING)
    monkeypatch.setattr(main_mod, "generate_briefing", lambda **_: existing)
    resp = client.post("/api/briefings")
    assert resp.status_code == 200
    assert resp.json()["id"] == existing["id"]


def test_generate_podcast_endpoint_success(client: TestClient, monkeypatch: Any) -> None:
    briefing = dict(_SAMPLE_BRIEFING)
    briefing["script"] = None
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: briefing)

    from pathlib import Path

    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = False
    monkeypatch.setattr("news_dashboard.tts._podcast_audio_path", lambda *_, **__: mock_path)

    monkeypatch.setattr(
        "news_dashboard.tts.generate_podcast_script",
        lambda *_, **__: [{"speaker": "Alex", "voice": "alloy", "text": "Hi"}],
    )
    monkeypatch.setattr("news_dashboard.briefings.update_briefing_script", lambda *_, **__: None)
    monkeypatch.setattr("news_dashboard.tts.generate_podcast_audio", lambda *_, **__: mock_path)

    resp = client.post("/api/briefings/1/podcast")
    assert resp.status_code == 200
    assert resp.json() == {"url": "/api/briefings/1/podcast"}


def test_get_podcast_audio_endpoint_success(
    client: TestClient, monkeypatch: Any, tmp_path: Path
) -> None:
    briefing = dict(_SAMPLE_BRIEFING)
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: briefing)

    audio_file = tmp_path / "podcast-1.mp3"
    audio_file.write_bytes(b"podcast-data")
    monkeypatch.setattr("news_dashboard.tts._podcast_audio_path", lambda *_, **__: audio_file)

    resp = client.get("/api/briefings/1/podcast")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.read() == b"podcast-data"


def test_get_podcast_audio_endpoint_not_found(client: TestClient, monkeypatch: Any) -> None:
    briefing = dict(_SAMPLE_BRIEFING)
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: briefing)

    from pathlib import Path

    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = False
    monkeypatch.setattr("news_dashboard.tts._podcast_audio_path", lambda *_, **__: mock_path)

    resp = client.get("/api/briefings/1/podcast")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "podcast audio file not found"


# ── POST /api/briefings/{id}/chat ─────────────────────────────────────────────


def test_chat_returns_reply_from_assistant(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        main_mod,
        "chat_with_briefing",
        lambda *_args, **_kwargs: "The layoffs were driven by cost cuts.",
    )
    resp = client.post(
        "/api/briefings/1/chat",
        json={"message": "Why did the company announce layoffs?", "history": []},
    )
    assert resp.status_code == 200
    assert resp.json() == {"reply": "The layoffs were driven by cost cuts."}


def test_chat_passes_history_to_backend(client: TestClient, monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def _fake(briefing_id: int, message: str, history: list[dict[str, str]], **_: Any) -> str:
        captured["briefing_id"] = briefing_id
        captured["message"] = message
        captured["history"] = history
        return "answer"

    monkeypatch.setattr(main_mod, "chat_with_briefing", _fake)
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! Ask me anything."},
    ]
    resp = client.post(
        "/api/briefings/7/chat",
        json={"message": "What happened in section 2?", "history": history},
    )
    assert resp.status_code == 200
    assert captured["briefing_id"] == 7
    assert captured["message"] == "What happened in section 2?"
    assert captured["history"] == history


def test_chat_returns_404_when_briefing_missing(client: TestClient, monkeypatch: Any) -> None:
    def _raise(*_: Any, **__: Any) -> str:
        msg = "briefing 99 not found"
        raise BriefingNotFoundError(msg)

    monkeypatch.setattr(main_mod, "chat_with_briefing", _raise)
    resp = client.post("/api/briefings/99/chat", json={"message": "hello", "history": []})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "briefing not found"


def test_chat_does_not_convert_unexpected_key_errors_to_404(
    client: TestClient, monkeypatch: Any
) -> None:
    def _raise(*_: Any, **__: Any) -> str:
        raise KeyError(0)

    monkeypatch.setattr(main_mod, "chat_with_briefing", _raise)

    with pytest.raises(KeyError, match="0"):
        client.post("/api/briefings/1/chat", json={"message": "hello", "history": []})


def test_chat_returns_503_when_ai_not_configured(client: TestClient, monkeypatch: Any) -> None:
    def _raise(*_: Any, **__: Any) -> str:
        msg = "OPENAI_API_KEY not set"
        raise BriefingAINotConfiguredError(msg)

    monkeypatch.setattr(main_mod, "chat_with_briefing", _raise)
    resp = client.post("/api/briefings/1/chat", json={"message": "hello", "history": []})
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]


# ── Payload bounds (#602) ─────────────────────────────────────────────────────


def test_chat_rejects_blank_message(client: TestClient) -> None:
    resp = client.post("/api/briefings/1/chat", json={"message": "   ", "history": []})
    assert resp.status_code == 422


def test_chat_rejects_oversized_message(client: TestClient) -> None:
    from news_dashboard.main import MAX_BRIEFING_CHAT_MESSAGE_LENGTH

    resp = client.post(
        "/api/briefings/1/chat",
        json={"message": "x" * (MAX_BRIEFING_CHAT_MESSAGE_LENGTH + 1), "history": []},
    )
    assert resp.status_code == 422


def test_chat_rejects_oversized_history(client: TestClient) -> None:
    from news_dashboard.main import MAX_BRIEFING_CHAT_HISTORY_ITEMS

    history = [{"role": "user", "content": "hi"}] * (MAX_BRIEFING_CHAT_HISTORY_ITEMS + 1)
    resp = client.post("/api/briefings/1/chat", json={"message": "hello", "history": history})
    assert resp.status_code == 422


def test_chat_accepts_message_at_length_boundary(client: TestClient, monkeypatch: Any) -> None:
    from news_dashboard.main import MAX_BRIEFING_CHAT_MESSAGE_LENGTH

    monkeypatch.setattr(main_mod, "chat_with_briefing", lambda *_args, **_kwargs: "ok")
    resp = client.post(
        "/api/briefings/1/chat",
        json={"message": "x" * MAX_BRIEFING_CHAT_MESSAGE_LENGTH, "history": []},
    )
    assert resp.status_code == 200


def test_create_rejects_oversized_focus_prompt(client: TestClient) -> None:
    from news_dashboard.main import MAX_BRIEFING_FOCUS_PROMPT_LENGTH

    resp = client.post(
        "/api/briefings",
        json={"focus_prompt": "x" * (MAX_BRIEFING_FOCUS_PROMPT_LENGTH + 1)},
    )
    assert resp.status_code == 422


def test_create_normalizes_blank_focus_prompt_to_none(client: TestClient, monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return dict(_SAMPLE_BRIEFING)

    monkeypatch.setattr(main_mod, "generate_briefing", _fake)
    resp = client.post("/api/briefings", json={"focus_prompt": "   "})
    assert resp.status_code == 200
    assert captured["focus_prompt"] is None


def test_chat_constructs_prompt_with_article_bodies(monkeypatch: Any) -> None:
    """Verify the system prompt includes briefing summary and article body text."""
    from unittest.mock import MagicMock, patch

    sample_briefing = dict(_SAMPLE_BRIEFING)
    article_body = "Detailed article body text about the announcement."

    captured_messages: list[Any] = []

    def fake_chat_create(client: Any, *, messages: list[Any], **kwargs: Any) -> Any:
        captured_messages.extend(messages)
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "grounded answer"
        return mock_response

    with (
        patch("news_dashboard.briefings.get_briefing", return_value=sample_briefing),
        patch("news_dashboard.briefings._briefing_ai_config", return_value=("key", None)),
        patch("news_dashboard.ai_client.get_openai_client", return_value=MagicMock()),
        patch("news_dashboard.ai_client.chat_create", side_effect=fake_chat_create),
        patch(
            "news_dashboard.briefings.connect",
        ) as mock_connect,
    ):
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = {"body": article_body}
        mock_connect.return_value = mock_conn

        from news_dashboard.briefings import chat_with_briefing

        reply = chat_with_briefing(1, "What are the benchmarks?", [], user_id=1)

    assert reply == "grounded answer"
    system_msg = next(m for m in captured_messages if m["role"] == "system")
    assert "AI Frameworks Tighten Production Workflows" in system_msg["content"]
    assert article_body in system_msg["content"]
