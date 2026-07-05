"""Tests for embedding retry/backoff and per-article backfill isolation (#1011)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from news_dashboard import embeddings as embeddings_mod
from news_dashboard.auth import require_auth
from news_dashboard.db import EMBEDDING_DIMENSIONS, connect, init_db
from news_dashboard.embeddings import (
    EmbeddingUnavailableError,
    _embed,
    embed_all_eligible,
)
from news_dashboard.main import app


def _rate_limit_error() -> openai.RateLimitError:
    response = httpx.Response(
        429, request=httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    )
    return openai.RateLimitError("rate limited", response=response, body=None)


class _FakeEmbeddingData:
    def __init__(self, value: float = 0.1) -> None:
        self.embedding = [value] * 10 + [0.0] * (EMBEDDING_DIMENSIONS - 10)


class _FakeEmbeddingResponse:
    def __init__(self, value: float = 0.1) -> None:
        self.data = [_FakeEmbeddingData(value)]


class _FlakyEmbeddings:
    """Raises RateLimitError *fail_times* times, then succeeds."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def create(self, **_: Any) -> _FakeEmbeddingResponse:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise _rate_limit_error()
        return _FakeEmbeddingResponse()


class _AlwaysRateLimitedEmbeddings:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **_: Any) -> _FakeEmbeddingResponse:
        self.calls += 1
        raise _rate_limit_error()


class _FakeClient:
    def __init__(self, embeddings: Any) -> None:
        self.embeddings = embeddings


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries should not actually slow down the test suite."""
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


@pytest.fixture(autouse=True)
def _embed_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


# ── _embed retry/backoff ────────────────────────────────────────────────────


def test_embed_retries_transient_rate_limit_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flaky = _FlakyEmbeddings(fail_times=2)
    monkeypatch.setattr(
        embeddings_mod, "_embeddings_ai_config", lambda: ("key", None, "text-embedding-3-small")
    )
    monkeypatch.setattr("news_dashboard.ai_client.get_chat_client", lambda **_: _FakeClient(flaky))
    vector = _embed("hello world")
    assert vector[0] == pytest.approx(0.1)
    assert flaky.calls == 3  # 2 failures + 1 success


def test_embed_raises_unavailable_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    always_limited = _AlwaysRateLimitedEmbeddings()
    monkeypatch.setattr(
        embeddings_mod, "_embeddings_ai_config", lambda: ("key", None, "text-embedding-3-small")
    )
    monkeypatch.setattr(
        "news_dashboard.ai_client.get_chat_client", lambda **_: _FakeClient(always_limited)
    )
    with pytest.raises(EmbeddingUnavailableError):
        _embed("hello world")
    assert always_limited.calls == embeddings_mod.EMBED_MAX_ATTEMPTS


def test_embed_does_not_retry_non_rate_limit_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BoomEmbeddings:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **_: Any) -> _FakeEmbeddingResponse:
            self.calls += 1
            message = "boom"
            raise RuntimeError(message)

    boom = _BoomEmbeddings()
    monkeypatch.setattr(
        embeddings_mod, "_embeddings_ai_config", lambda: ("key", None, "text-embedding-3-small")
    )
    monkeypatch.setattr("news_dashboard.ai_client.get_chat_client", lambda **_: _FakeClient(boom))
    with pytest.raises(RuntimeError, match="boom"):
        _embed("hello world")
    assert boom.calls == 1


# ── embed_all_eligible per-article isolation ────────────────────────────────


def _seed_source(db_path: Path, slug: str = "test-source") -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, 'engineering', 'rss', 50, TRUE)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, "TestSource", f"https://example.com/{slug}.xml"),
        )


def _seed_unembedded_articles(db_path: Path, count: int) -> list[int]:
    init_db(db_path)
    _seed_source(db_path)
    ids = []
    with connect(db_path) as conn:
        for i in range(1, count + 1):
            row = conn.execute(
                """
                INSERT INTO articles(
                    url, canonical_url, title, source_slug, source_name,
                    category, kind, status, importance_score, summary, reason, tags
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'saved', %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    f"https://example.com/{i}",
                    f"https://example.com/{i}",
                    f"Article {i}",
                    "test-source",
                    "TestSource",
                    "engineering",
                    "rss",
                    0.5,
                    f"Summary {i}",
                    "",
                    "",
                ),
            ).fetchone()
            ids.append(row["id"])
    return ids


def test_embed_all_eligible_skips_failing_article_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "embed.db"
    ids = _seed_unembedded_articles(db_path, count=3)
    failing_id = ids[1]

    def _fake_embed(text: str) -> list[float]:
        if f"Article {ids.index(failing_id) + 1}" in text:
            message = "embedding provider rate-limited after 4 attempts"
            raise EmbeddingUnavailableError(message)
        return [0.1] * 10 + [0.0] * (EMBEDDING_DIMENSIONS - 10)

    monkeypatch.setattr(embeddings_mod, "_embed", _fake_embed)

    count = embed_all_eligible(db_path)
    assert count == 2  # the failing article is skipped, the other two succeed

    with connect(db_path) as conn:
        embedded_ids = {
            row["id"]
            for row in conn.execute(
                "SELECT id FROM articles WHERE embedding_vec IS NOT NULL"
            ).fetchall()
        }
    assert embedded_ids == {ids[0], ids[2]}


# ── /api/ask surfaces a clean error on persistent embedding failure ────────


def test_ask_endpoint_returns_503_when_embedding_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(_query: str, **_: Any) -> dict[str, Any]:
        message = "embedding provider rate-limited after 4 attempts: rate limited"
        raise EmbeddingUnavailableError(message)

    monkeypatch.setattr("news_dashboard.embeddings.ask", _boom)

    http = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides[require_auth] = lambda: {
        "id": 1,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    try:
        response = http.post("/api/ask", json={"query": "what happened today?"})
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 503
    body = response.json()
    assert "temporarily unavailable" in body["detail"]
    assert "rate limited" not in body["detail"]
