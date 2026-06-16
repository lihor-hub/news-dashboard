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

from typing import Any

from fastapi.testclient import TestClient

import news_dashboard.main as main_mod
from news_dashboard.briefings import BriefingAINotConfiguredError, BriefingGenerationError
from news_dashboard.db import POSTGRES_SCHEMA
from news_dashboard.main import app

client = TestClient(app, raise_server_exceptions=True)

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


def test_latest_empty_state_when_no_briefing(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_latest_briefing", lambda **_: None)
    resp = client.get("/api/briefings/latest")
    assert resp.status_code == 200
    assert resp.json() == {"status": "empty"}


# ── GET /api/briefings/latest — with a saved briefing ────────────────────────


def test_latest_returns_briefing_metadata(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_latest_briefing", lambda **_: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert data["title"] == "AI Frameworks Tighten Production Workflows"
    assert data["status"] == "complete"


def test_latest_returns_structured_content(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_latest_briefing", lambda **_: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/latest")
    data = resp.json()
    assert "content" in data
    assert "sections" in data["content"]
    assert len(data["content"]["sections"]) == 1
    assert data["content"]["worth_opening"] == [42]


def test_latest_returns_cited_article_metadata(monkeypatch: Any) -> None:
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


def test_list_returns_items_key(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "list_briefings", lambda **_: [dict(_SAMPLE_LIST_ITEM)])
    resp = client.get("/api/briefings")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == 1


def test_list_empty_when_no_briefings(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "list_briefings", lambda **_: [])
    resp = client.get("/api/briefings")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_list_items_omit_content_blob(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "list_briefings", lambda **_: [dict(_SAMPLE_LIST_ITEM)])
    resp = client.get("/api/briefings")
    item = resp.json()["items"][0]
    assert "content" not in item
    assert "articles" not in item


def test_list_respects_limit_and_offset_params(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def _mock(**kw: Any) -> list[dict[str, Any]]:
        captured.update(kw)
        return []

    monkeypatch.setattr(main_mod, "list_briefings", _mock)
    client.get("/api/briefings?limit=10&offset=20")
    assert captured.get("limit") == 10
    assert captured.get("offset") == 20


# ── GET /api/briefings/{id} — detail ─────────────────────────────────────────


def test_detail_returns_full_briefing_with_articles(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert "content" in data
    assert len(data["articles"]) == 1


def test_detail_404_for_missing_briefing(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: None)
    resp = client.get("/api/briefings/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "briefing not found"


def test_detail_passes_id_to_backend(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def _mock(bid: int, **_: Any) -> dict[str, Any] | None:
        captured["bid"] = bid
        return dict(_SAMPLE_BRIEFING)

    monkeypatch.setattr(main_mod, "get_briefing", _mock)
    client.get("/api/briefings/7")
    assert captured["bid"] == 7


def test_detail_returns_scope_and_time_window(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/1")
    data = resp.json()
    assert data["scope"] == "since_last_briefing"
    assert data["since_at"] is not None
    assert data["until_at"] is not None


def test_detail_cited_article_has_section_and_citation_index(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "get_briefing", lambda _, **__: dict(_SAMPLE_BRIEFING))
    resp = client.get("/api/briefings/1")
    article = resp.json()["articles"][0]
    assert "section_index" in article
    assert "citation_index" in article


# ── POST /api/briefings — generate ───────────────────────────────────────────


def test_create_returns_briefing_on_success(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "generate_briefing", lambda **_: dict(_SAMPLE_BRIEFING))
    resp = client.post("/api/briefings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert data["status"] == "complete"
    assert "articles" in data


def test_create_returns_no_candidates_when_no_today_articles(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "generate_briefing", lambda **_: {"status": "no_candidates"})
    resp = client.post("/api/briefings")
    assert resp.status_code == 200
    assert resp.json() == {"status": "no_candidates"}


def test_create_returns_503_when_ai_not_configured(monkeypatch: Any) -> None:
    def _raise(**_: Any) -> dict[str, Any]:
        msg = "OPENAI_API_KEY not set"
        raise BriefingAINotConfiguredError(msg)

    monkeypatch.setattr(main_mod, "generate_briefing", _raise)
    resp = client.post("/api/briefings")
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]


def test_create_returns_500_when_generation_fails(monkeypatch: Any) -> None:
    def _raise(**_: Any) -> dict[str, Any]:
        msg = "AI returned invalid JSON"
        raise BriefingGenerationError(msg)

    monkeypatch.setattr(main_mod, "generate_briefing", _raise)
    resp = client.post("/api/briefings")
    assert resp.status_code == 500
    assert "invalid JSON" in resp.json()["detail"]


def test_create_returns_content_and_articles_on_success(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod, "generate_briefing", lambda **_: dict(_SAMPLE_BRIEFING))
    resp = client.post("/api/briefings")
    data = resp.json()
    assert "content" in data
    assert "sections" in data["content"]
    assert "articles" in data
    assert len(data["articles"]) > 0


def test_create_returns_existing_briefing_inside_idempotency_window(monkeypatch: Any) -> None:
    existing = dict(_SAMPLE_BRIEFING)
    monkeypatch.setattr(main_mod, "generate_briefing", lambda **_: existing)
    resp = client.post("/api/briefings")
    assert resp.status_code == 200
    assert resp.json()["id"] == existing["id"]
