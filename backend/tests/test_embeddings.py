"""Tests for embedding retry/backoff and per-article backfill isolation (#1011)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
from unittest.mock import MagicMock

import httpx2
import openai
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

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
    response = httpx2.Response(
        429, request=httpx2.Request("POST", "https://api.openai.com/v1/embeddings")
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


def _seed_unembedded_articles(db_path: Any, count: int) -> list[int]:
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


def test_embed_all_eligible_limits_backfill_in_postgres(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _seed_unembedded_articles(pg_clean, count=20)
    monkeypatch.setattr(
        embeddings_mod,
        "_embed",
        lambda _text, **_kwargs: [0.1] * EMBEDDING_DIMENSIONS,
    )

    count = embed_all_eligible(pg_clean, max_articles=16)

    assert count == 16
    with connect(database_url=pg_clean) as conn:
        embedded = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM articles WHERE embedding_vec IS NOT NULL ORDER BY id"
            ).fetchall()
        ]
    assert embedded == ids[:16]


def test_mcp_execution_policy_bounds_provider_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.assistant.service import AskExecutionPolicy

    captured_client: dict[str, Any] = {}
    captured_model: dict[str, Any] = {}

    class FakeEmbeddingData:
        def __init__(self) -> None:
            self.embedding = [0.1]

    class FakeEmbeddings:
        def create(self, **_kwargs: Any) -> Any:
            return type("Response", (), {"data": [FakeEmbeddingData()]})()

    class FakeClient:
        embeddings = FakeEmbeddings()

    def fake_client(**kwargs: Any) -> FakeClient:
        captured_client.update(kwargs)
        return FakeClient()

    monkeypatch.setattr(embeddings_mod, "_embeddings_ai_config", lambda: ("key", None, "embed"))
    monkeypatch.setattr("news_dashboard.ai_client.get_chat_client", fake_client)
    embeddings_mod._embed("question", timeout_seconds=20.0, trace_content=False)
    assert captured_client["timeout_seconds"] == 20.0
    assert captured_client["enable_tracing"] is False

    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setattr(
        "news_dashboard.ai_client.get_chat_model",
        lambda **kwargs: (
            captured_model.update(kwargs)
            or RunnableLambda(lambda _value: AIMessage(content="answer"))
        ),
    )
    policy = AskExecutionPolicy.mcp()
    embeddings_mod._answer(
        "system",
        "user",
        max_tokens=policy.answer_max_tokens,
        timeout_seconds=policy.provider_timeout_seconds,
    )
    assert captured_model["max_tokens"] == 512
    assert captured_model["timeout_seconds"] == 20.0


def test_private_backfill_logs_no_article_or_provider_content(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ids = _seed_unembedded_articles(pg_clean, count=1)
    hostile = "PRIVATE PROVIDER BODY"

    def fail_privately(_text: str, **_kwargs: Any) -> list[float]:
        raise RuntimeError(hostile)

    monkeypatch.setattr(embeddings_mod, "_embed", fail_privately)
    with caplog.at_level(logging.WARNING, logger="news_dashboard.embeddings"):
        count = embed_all_eligible(
            pg_clean,
            max_articles=16,
            provider_timeout_seconds=20.0,
            trace_content=False,
        )

    assert count == 0
    rendered = caplog.text
    assert hostile not in rendered
    assert str(ids[0]) not in rendered


def test_private_embedding_records_safe_provider_usage_at_client_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard import ai_client

    observation = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = observation
    client = MagicMock()
    client.start_as_current_observation.return_value = context
    response = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.1, 0.2])],
        usage=SimpleNamespace(prompt_tokens=7, total_tokens=7),
    )
    plain = MagicMock()
    plain.embeddings.create.return_value = response
    monkeypatch.setattr(ai_client, "langfuse_enabled", lambda: True)
    monkeypatch.setattr(ai_client, "_client", lambda: client)
    monkeypatch.setattr(ai_client, "get_openai_client", lambda **_kwargs: plain)
    monkeypatch.setattr(
        embeddings_mod, "_embeddings_ai_config", lambda: ("secret", None, "embed-model")
    )

    vector = embeddings_mod._embed("PRIVATE INPUT", timeout_seconds=20.0, trace_content=False)

    assert vector == [0.1, 0.2]
    client.start_as_current_observation.assert_called_once_with(
        name="query-embedding-primary",
        as_type="embedding",
        input=None,
        model="embed-model",
        model_parameters={},
        metadata={
            "operation": "query-embedding",
            "provider": "primary",
            "attempt": 1,
            "retry": 0,
        },
    )
    observation.update.assert_called_once_with(
        output={"status": "ok"},
        usage_details={"input": 7, "total": 7},
        metadata={
            "operation": "query-embedding",
            "provider": "primary",
            "attempt": 1,
            "retry": 0,
            "outcome": "success",
        },
    )
    rendered = repr((client.mock_calls, observation.mock_calls))
    assert "PRIVATE INPUT" not in rendered
    assert "secret" not in rendered


def test_private_answer_records_safe_generation_usage_at_client_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard import ai_client

    observation = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = observation
    langfuse = MagicMock()
    langfuse.start_as_current_observation.return_value = context
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="PRIVATE ANSWER"))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4, total_tokens=15, cost=0.002),
    )
    plain = MagicMock()
    plain.chat.completions.create.return_value = response
    monkeypatch.setattr(ai_client, "langfuse_enabled", lambda: True)
    monkeypatch.setattr(ai_client, "_client", lambda: langfuse)
    monkeypatch.setattr(ai_client, "get_openai_client", lambda **_kwargs: plain)
    monkeypatch.setattr(ai_client, "free_llm_config", lambda: ("secret", None))

    answer = embeddings_mod._answer(
        "PRIVATE SYSTEM",
        "PRIVATE USER PROMPT",
        max_tokens=512,
        timeout_seconds=20.0,
        trace_content=False,
    )

    assert answer == "PRIVATE ANSWER"
    langfuse.start_as_current_observation.assert_called_once_with(
        name="answer-generation-primary",
        as_type="generation",
        input=None,
        model="gpt-4o-mini",
        model_parameters={"max_tokens": 512},
        metadata={
            "operation": "answer-generation",
            "provider": "primary",
            "attempt": 1,
            "retry": 0,
        },
    )
    observation.update.assert_called_once_with(
        output={"status": "ok"},
        usage_details={"input": 11, "output": 4, "total": 15},
        metadata={
            "operation": "answer-generation",
            "provider": "primary",
            "attempt": 1,
            "retry": 0,
            "outcome": "success",
        },
        cost_details={"total": 0.002},
    )
    rendered = repr((langfuse.mock_calls, observation.mock_calls))
    for secret in ("PRIVATE SYSTEM", "PRIVATE USER PROMPT", "PRIVATE ANSWER", "secret"):
        assert secret not in rendered


def test_private_ask_root_exits_cleanly_and_returns_trace_for_small_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard import ai_client
    from news_dashboard.assistant.service import AskExecutionPolicy

    escaped: list[BaseException | None] = []
    root = MagicMock()

    class CleanExitContext:
        def __enter__(self) -> MagicMock:
            return root

        def __exit__(
            self, _kind: Any, error: BaseException | None, _traceback: Any
        ) -> Literal[False]:
            escaped.append(error)
            return False

    client = MagicMock()
    client.start_as_current_observation.return_value = CleanExitContext()
    client.get_current_trace_id.return_value = "0123456789abcdef0123456789abcdef"
    monkeypatch.setattr(ai_client, "langfuse_enabled", lambda: True)
    monkeypatch.setattr(ai_client, "_client", lambda: client)
    monkeypatch.setattr(
        embeddings_mod,
        "_ask_impl",
        lambda *_args, **_kwargs: {
            "answer": "Not enough articles",
            "sources": [],
            "trace_id": None,
        },
    )

    result = embeddings_mod.ask(
        "PRIVATE QUESTION", user_id=7, execution_policy=AskExecutionPolicy.mcp()
    )

    assert escaped == [None]
    assert result["trace_id"] == "0123456789abcdef0123456789abcdef"
    root.update.assert_called_once_with(
        output={"answer_chars": 19, "source_count": 0, "status": "ok"}
    )


def test_private_ask_root_reraises_only_after_clean_observation_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard import ai_client
    from news_dashboard.assistant.service import AskExecutionPolicy

    escaped: list[BaseException | None] = []
    root = MagicMock()

    class CleanExitContext:
        def __enter__(self) -> MagicMock:
            return root

        def __exit__(
            self, _kind: Any, error: BaseException | None, _traceback: Any
        ) -> Literal[False]:
            escaped.append(error)
            return False

    client = MagicMock()
    client.start_as_current_observation.return_value = CleanExitContext()
    monkeypatch.setattr(ai_client, "langfuse_enabled", lambda: True)
    monkeypatch.setattr(ai_client, "_client", lambda: client)
    hostile = "provider=https://secret sql=SELECT bearer=private"

    def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(hostile)

    monkeypatch.setattr(embeddings_mod, "_ask_impl", fail)
    with pytest.raises(RuntimeError, match="provider=https://secret"):
        embeddings_mod.ask("PRIVATE QUESTION", user_id=7, execution_policy=AskExecutionPolicy.mcp())

    assert escaped == [None]
    root.update.assert_called_once_with(
        output={"status": "error"}, level="ERROR", status_message="ask failed"
    )
    assert hostile not in repr(root.mock_calls)


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


def test_ask_includes_bounded_graph_context(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db(pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind)
            VALUES ('ask-graph', 'AskGraph', 'https://example.test/feed.xml', 'tech', 'rss_feed')
            ON CONFLICT(slug) DO NOTHING
            """
        )
        for article_id in range(1, 6):
            conn.execute(
                """
                INSERT INTO articles(
                    id, url, canonical_url, title, source_slug, source_name,
                    category, kind, status, importance_score, summary, reason,
                    tags, embedding_vec
                ) VALUES (%s, %s, %s, %s, 'ask-graph', 'AskGraph',
                    'tech', 'rss_feed', 'saved', 0.5, %s, '', '', %s::vector)
                """,
                (
                    article_id,
                    f"https://example.test/{article_id}",
                    f"https://example.test/{article_id}",
                    f"Article {article_id}",
                    f"Summary {article_id}",
                    "[" + ",".join(["0.1"] * EMBEDDING_DIMENSIONS) + "]",
                ),
            )

    captured: dict[str, str] = {}
    graph_context = {
        "entities": [{"id": "org:openai", "name": "OpenAI", "type": "org", "article_ids": [1]}],
        "relationships": [
            {
                "source": "org:openai",
                "source_name": "OpenAI",
                "target": "person:sam-altman",
                "target_name": "Sam Altman",
                "label": "led by",
                "relationship_type": "led_by",
                "article_ids": [1],
            }
        ],
    }

    def fake_answer(
        _system_prompt: str,
        user_prompt: str,
        **_kwargs: Any,
    ) -> str:
        captured["prompt"] = user_prompt
        return "graph answer"

    monkeypatch.setattr(embeddings_mod, "embed_all_eligible", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(embeddings_mod, "_embed", lambda _query: [0.1] * EMBEDDING_DIMENSIONS)
    monkeypatch.setattr(embeddings_mod, "_answer", fake_answer)
    monkeypatch.setattr(
        embeddings_mod,
        "graph_context_for_articles",
        lambda article_ids: graph_context if article_ids else None,
    )

    result = embeddings_mod.ask("who leads OpenAI?", pg_clean)

    assert result["answer"] == "graph answer"
    assert result["graph_context"] == graph_context
    assert "Knowledge graph:" in captured["prompt"]
    assert "OpenAI led by Sam Altman" in captured["prompt"]
    assert "articles [1]" in captured["prompt"]
