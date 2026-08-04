"""Tests for /api/ask retrieval scope — default (Starred+Done) vs include_all."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from news_dashboard.db import EMBEDDING_DIMENSIONS, connect, init_db
from news_dashboard.embeddings import vector_literal


@pytest.fixture(autouse=True)
def _clean_postgres(pg_clean: str) -> None:
    """Isolate legacy tmp-path call sites on the PostgreSQL test schema."""


def _test_vector(value: float = 0.1, dims: int = 10) -> str:
    """A pgvector literal padded to the real embedding_vec(1536) width.

    Trailing zeros don't change cosine similarity/ordering, so tests can keep
    seeding short, readable vectors.
    """
    vec = [value] * dims + [0.0] * (EMBEDDING_DIMENSIONS - dims)
    return vector_literal(vec)


def _seed_source(db_path: Any, slug: str = "test-source", name: str = "TestSource") -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, 'engineering', 'rss', 50, TRUE)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, name, f"https://example.com/{slug}.xml"),
        )


def _seed_articles(db_path: Path) -> None:
    """Insert one article per legacy status with a pre-set embedding."""
    init_db(db_path)
    _seed_source(db_path)
    embedding = _test_vector()
    statuses = ["new", "saved", "read", "skipped", "archived"]
    with connect(db_path) as conn:
        for i, status in enumerate(statuses, start=1):
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
                    "TestSource",
                    "engineering",
                    "rss",
                    status,
                    0.5,
                    f"Summary {i}",
                    "",
                    "",
                    embedding,
                ),
            )


def _make_openai_stub(monkeypatch: pytest.MonkeyPatch, answer: str = "ok") -> None:
    """Patch the native embedding client and LangChain answer model."""

    class FakeEmbeddingData:
        def __init__(self) -> None:
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


def _ids_in_pool(db_path: Path, include_all: bool) -> set[int]:
    """Return article IDs that ask() would retrieve for the given scope."""
    status_filter = "status != 'archived'" if include_all else "status IN ('saved', 'read')"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT id FROM articles WHERE {status_filter} AND embedding_vec IS NOT NULL"
        ).fetchall()
    return {row["id"] for row in rows}


# ─── Scope tests ──────────────────────────────────────────────────────────────


def test_default_scope_includes_only_starred_and_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default scope (include_all=False) only covers saved+read articles."""
    _seed_articles(tmp_path / "ask.db")
    pool = _ids_in_pool(tmp_path / "ask.db", include_all=False)
    # id 2 = saved (starred proxy), id 3 = read (done)
    assert pool == {2, 3}


def test_include_all_scope_excludes_only_archived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """include_all=True scope covers all non-archived articles."""
    _seed_articles(tmp_path / "ask.db")
    pool = _ids_in_pool(tmp_path / "ask.db", include_all=True)
    # id 5 = archived — must be excluded; ids 1-4 included
    assert 5 not in pool
    assert {1, 2, 3, 4}.issubset(pool)


def test_ask_default_scope_returns_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ask() with include_all=False succeeds when saved+read count >= MIN_ARTICLES."""
    db_path = tmp_path / "ask.db"
    init_db(db_path)
    _seed_source(db_path, "s", "S")
    embedding = _test_vector()
    with connect(db_path) as conn:
        for i in range(1, 8):  # 7 saved/read articles — above MIN_ARTICLES=5
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
                    "s",
                    "S",
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

    _make_openai_stub(monkeypatch, answer="test answer")
    from news_dashboard.embeddings import ask

    result = ask("what did I read?", db_path)
    assert result["answer"] == "test answer"
    assert len(result["sources"]) > 0


def test_ask_returns_not_enough_when_below_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ask() returns the 'not enough articles' message when corpus is too small."""
    db_path = tmp_path / "ask.db"
    _seed_articles(db_path)
    _make_openai_stub(monkeypatch)
    from news_dashboard.embeddings import ask

    result = ask("anything?", db_path)
    # Only 2 articles in default scope (saved+read) — below MIN_ARTICLES=5
    assert "Not enough articles" in result["answer"]
    assert result["sources"] == []


def test_ask_include_all_widens_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ask(include_all=True) includes new+skipped articles in the pool."""
    db_path = tmp_path / "ask.db"
    init_db(db_path)
    _seed_source(db_path, "s", "S")
    embedding = _test_vector()
    # Insert 6 articles with status 'new' — not picked up by default scope
    with connect(db_path) as conn:
        for i in range(1, 7):
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
                    "s",
                    "S",
                    "engineering",
                    "rss",
                    "new",
                    0.5,
                    f"Summary {i}",
                    "",
                    "",
                    embedding,
                ),
            )

    _make_openai_stub(monkeypatch, answer="widened answer")
    from news_dashboard.embeddings import ask

    # Default scope: 0 new articles in pool → not enough
    default_result = ask("anything?", db_path)
    assert "Not enough articles" in default_result["answer"]

    # include_all: 6 'new' articles → enough
    all_result = ask("anything?", db_path, include_all=True)
    assert all_result["answer"] == "widened answer"


# ─── User-scoped retrieval tests ──────────────────────────────────────────────


def _seed_user(db_path: Any, username: str) -> int:
    """Insert a user and return the generated id."""
    with connect(db_path) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'x') RETURNING id",
            (username,),
        ).fetchone()
    return int(row["id"])


def _seed_article_with_embedding(
    db_path: Any,
    article_id: int,
    source_slug: str = "test-source",
    source_name: str = "TestSource",
    legacy_status: str = "new",
    *,
    embedded: bool = True,
) -> None:
    embedding = _test_vector() if embedded else None
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO articles(
                id, url, canonical_url, title, source_slug, source_name,
                category, kind, status, importance_score, summary, reason,
                tags, embedding_vec
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            """,
            (
                article_id,
                f"https://example.com/{article_id}",
                f"https://example.com/{article_id}",
                f"Article {article_id}",
                source_slug,
                source_name,
                "engineering",
                "rss",
                legacy_status,
                0.5,
                f"Summary {article_id}",
                "",
                "",
                embedding,
            ),
        )


def _set_user_article_state(db_path: Any, user_id: int, article_id: int, state: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, state) VALUES (%s, %s, %s)"
            " ON CONFLICT(user_id, article_id) DO UPDATE SET state = EXCLUDED.state",
            (user_id, article_id, state),
        )


def test_ask_default_scope_uses_user_article_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default scope uses user_article_state (done/starred), not legacy articles.status."""
    db_path = tmp_path / "ask_uas.db"
    init_db(db_path)
    _seed_source(db_path)
    user_id = _seed_user(db_path, "user1")

    # 5 articles with legacy status 'new' — invisible to legacy scope
    for i in range(1, 6):
        _seed_article_with_embedding(db_path, i, legacy_status="new")
    # Mark all 5 as done for this user
    for i in range(1, 6):
        _set_user_article_state(db_path, user_id, i, "done")

    _make_openai_stub(monkeypatch, answer="user scoped answer")
    from news_dashboard.embeddings import ask

    # Without user_id: legacy path sees 0 eligible (all 'new') → not enough
    legacy_result = ask("question", db_path)
    assert "Not enough articles" in legacy_result["answer"]

    # With user_id: user_article_state says done → 5 eligible → answer
    user_result = ask("question", db_path, user_id=user_id)
    assert user_result["answer"] == "user scoped answer"


def test_ask_does_not_cross_user_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ask() for user1 cannot retrieve articles that only user2 has marked done."""
    db_path = tmp_path / "ask_cross.db"
    init_db(db_path)
    _seed_source(db_path)
    user1 = _seed_user(db_path, "user1")
    user2 = _seed_user(db_path, "user2")

    # 5 articles, only user2 marks them done
    for i in range(1, 6):
        _seed_article_with_embedding(db_path, i)
        _set_user_article_state(db_path, user2, i, "done")

    _make_openai_stub(monkeypatch, answer="user2 answer")
    from news_dashboard.embeddings import ask

    # user1 sees no done/starred articles → not enough
    result_user1 = ask("question", db_path, user_id=user1)
    assert "Not enough articles" in result_user1["answer"]

    # user2 sees 5 done articles → answer
    result_user2 = ask("question", db_path, user_id=user2)
    assert result_user2["answer"] == "user2 answer"


def test_ask_include_all_excludes_user_archived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ask(include_all=True) excludes articles archived by the requesting user."""
    db_path = tmp_path / "ask_arch.db"
    init_db(db_path)
    _seed_source(db_path)
    user_id = _seed_user(db_path, "user1")

    # 6 articles visible in include_all scope; archive the last one for user
    for i in range(1, 7):
        _seed_article_with_embedding(db_path, i)
    _set_user_article_state(db_path, user_id, 6, "archived")

    _make_openai_stub(monkeypatch, answer="include_all answer")
    from news_dashboard.embeddings import ask

    result = ask("question", db_path, include_all=True, user_id=user_id)
    assert result["answer"] == "include_all answer"
    source_ids = {s["id"] for s in result["sources"]}
    assert 6 not in source_ids


def test_ask_respects_disabled_user_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ask() excludes articles from sources the user has explicitly disabled."""
    db_path = tmp_path / "ask_srcdis.db"
    init_db(db_path)
    _seed_source(db_path, "source-a", "Source A")
    _seed_source(db_path, "source-b", "Source B")
    user_id = _seed_user(db_path, "user1")

    # 5 articles from source-a, 1 from source-b; user has done all
    for i in range(1, 6):
        _seed_article_with_embedding(db_path, i, source_slug="source-a", source_name="Source A")
        _set_user_article_state(db_path, user_id, i, "done")
    _seed_article_with_embedding(db_path, 6, source_slug="source-b", source_name="Source B")
    _set_user_article_state(db_path, user_id, 6, "done")

    # Disable source-b for user1
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (%s, %s, %s)",
            (user_id, "source-b", False),
        )

    _make_openai_stub(monkeypatch, answer="filtered answer")
    from news_dashboard.embeddings import ask

    result = ask("question", db_path, user_id=user_id)
    assert result["answer"] == "filtered answer"
    source_ids = {s["id"] for s in result["sources"]}
    assert 6 not in source_ids


def test_mcp_policy_preserves_exact_two_user_visibility_corpora(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCP bounds must not weaken the canonical per-user visibility predicates."""
    from news_dashboard.assistant.service import AskExecutionPolicy
    from news_dashboard.embeddings import ask

    init_db(pg_clean)
    alice = _seed_user(pg_clean, "alice-policy")
    bob = _seed_user(pg_clean, "bob-policy")
    _seed_source(pg_clean, "global", "Global")
    _seed_source(pg_clean, "disabled", "Disabled")
    _seed_source(pg_clean, "alice-private", "Alice Private")
    _seed_source(pg_clean, "bob-private", "Bob Private")
    with connect(database_url=pg_clean) as conn:
        conn.execute("UPDATE sources SET owner_user_id=%s WHERE slug='alice-private'", (alice,))
        conn.execute("UPDATE sources SET owner_user_id=%s WHERE slug='bob-private'", (bob,))
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled) "
            "VALUES (%s, 'disabled', FALSE)",
            (alice,),
        )

    article_sources = {
        1: "global",
        2: "global",
        3: "global",
        4: "global",
        5: "global",
        6: "global",
        7: "disabled",
        8: "alice-private",
        9: "alice-private",
        10: "bob-private",
    }
    for article_id, source_slug in article_sources.items():
        _seed_article_with_embedding(
            pg_clean,
            article_id,
            source_slug=source_slug,
            source_name=source_slug,
            embedded=False,
        )
    for article_id in (1, 2, 3, 4, 5, 7, 8, 10):
        _set_user_article_state(pg_clean, alice, article_id, "done")
    _set_user_article_state(pg_clean, alice, 6, "archived")
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "UPDATE user_article_state SET starred=TRUE WHERE user_id=%s AND article_id IN (2, 8)",
            (alice,),
        )

    embedded_inputs: list[str] = []
    answer_messages: list[dict[str, str]] = []

    class FakeEmbeddings:
        def create(self, **kwargs: Any) -> Any:
            embedded_inputs.append(str(kwargs["input"]))
            return type(
                "EmbeddingResponse",
                (),
                {
                    "data": [
                        type(
                            "EmbeddingData",
                            (),
                            {"embedding": [0.1] * EMBEDDING_DIMENSIONS},
                        )()
                    ],
                    "usage": type("Usage", (), {"prompt_tokens": 1, "total_tokens": 1})(),
                },
            )()

    class FakeCompletions:
        def create(self, **kwargs: Any) -> Any:
            answer_messages.extend(kwargs["messages"])
            return type(
                "ChatResponse",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {"message": type("Message", (), {"content": "bounded answer"})()},
                        )()
                    ],
                    "usage": type(
                        "Usage",
                        (),
                        {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                    )(),
                },
            )()

    client = type(
        "FakeOpenAI",
        (),
        {
            "embeddings": FakeEmbeddings(),
            "chat": type("Chat", (), {"completions": FakeCompletions()})(),
        },
    )()
    monkeypatch.setenv("FREE_LLM_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("news_dashboard.ai_client.get_openai_client", lambda **_kwargs: client)
    policy = AskExecutionPolicy.mcp()
    saved = ask("question", pg_clean, user_id=alice, execution_policy=policy)
    first_backfill = [text for text in embedded_inputs if text.startswith("Article")]
    visible = ask(
        "question",
        pg_clean,
        user_id=alice,
        include_all=True,
        execution_policy=policy,
    )

    assert {source["id"] for source in saved["sources"]} == {1, 2, 3, 4, 5, 8}
    assert {source["id"] for source in visible["sources"]} == {1, 2, 3, 4, 5, 8, 9}
    forbidden = {6, 7, 10}
    assert forbidden.isdisjoint(source["id"] for source in saved["sources"])
    assert forbidden.isdisjoint(source["id"] for source in visible["sources"])
    assert len(first_backfill) <= 16
    second_backfill = [
        text for text in embedded_inputs[len(first_backfill) :] if text.startswith("Article")
    ]
    assert len(second_backfill) <= 16
    provider_content = repr((embedded_inputs, answer_messages))
    for forbidden_id in forbidden:
        for secret in (
            f"Article {forbidden_id}",
            f"Summary {forbidden_id}",
            f"https://example.com/{forbidden_id}",
        ):
            assert secret not in provider_content


# ── POST /api/ask — payload bounds (#602) ────────────────────────────────────


@pytest.fixture
def api_client() -> TestClient:
    from news_dashboard.main import app

    return TestClient(app, raise_server_exceptions=True)


def test_ask_endpoint_rejects_oversized_query(api_client: TestClient) -> None:
    from news_dashboard.assistant.models import MAX_ASK_QUERY_LENGTH

    resp = api_client.post(
        "/api/ask",
        json={"query": "x" * (MAX_ASK_QUERY_LENGTH + 1)},
    )
    assert resp.status_code == 422


def test_ask_endpoint_rejects_blank_query(api_client: TestClient) -> None:
    resp = api_client.post("/api/ask", json={"query": "   "})
    assert resp.status_code == 400


def test_ask_endpoint_threads_optional_session_id(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_ask(query: str, **kwargs: Any) -> dict[str, Any]:
        captured["query"] = query
        captured.update(kwargs)
        return {"answer": "ok", "sources": [], "trace_id": None}

    monkeypatch.setattr("news_dashboard.assistant.service.ask", fake_ask)
    response = api_client.post(
        "/api/ask", json={"query": "question", "session_id": "conversation-42"}
    )

    assert response.status_code == 200
    assert captured["session_id"] == "conversation-42"


def test_ask_endpoint_remains_compatible_without_session_id(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_ask(_query: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"answer": "ok", "sources": [], "trace_id": None}

    monkeypatch.setattr("news_dashboard.assistant.service.ask", fake_ask)
    response = api_client.post("/api/ask", json={"query": "question"})

    assert response.status_code == 200
    assert captured["session_id"] is None


@pytest.mark.parametrize("session_id", ["café", "x" * 200])
def test_ask_endpoint_rejects_invalid_session_id(api_client: TestClient, session_id: str) -> None:
    response = api_client.post("/api/ask", json={"query": "question", "session_id": session_id})
    assert response.status_code == 422
