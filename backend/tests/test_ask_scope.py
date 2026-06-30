"""Tests for /api/ask retrieval scope — default (Starred+Done) vs include_all."""

from __future__ import annotations

import struct
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from news_dashboard.db import connect, init_db


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _seed_source(db_path: Path, slug: str = "test-source", name: str = "TestSource") -> None:
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
    embedding = _pack([0.1] * 10)
    statuses = ["new", "saved", "read", "skipped", "archived"]
    with connect(db_path) as conn:
        for i, status in enumerate(statuses, start=1):
            conn.execute(
                """
                INSERT INTO articles(
                    id, url, canonical_url, title, source_slug, source_name,
                    category, kind, status, importance_score, summary, reason,
                    tags, embedding
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    """Patch openai so _embed and _answer don't hit the network."""

    class FakeMessage:
        content = answer

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = (FakeChoice(),)

    class FakeCompletions:
        def create(self, **_: Any) -> FakeResponse:
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeEmbeddingData:
        def __init__(self) -> None:
            self.embedding = [0.1] * 10

    class FakeEmbeddingResponse:
        def __init__(self) -> None:
            self.data = [FakeEmbeddingData()]

    class FakeEmbeddings:
        def create(self, **_: Any) -> FakeEmbeddingResponse:
            return FakeEmbeddingResponse()

    class FakeOpenAI:
        def __init__(self, **_: object) -> None:
            self.chat = FakeChat()
            self.embeddings = FakeEmbeddings()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def _ids_in_pool(db_path: Path, include_all: bool) -> set[int]:
    """Return article IDs that ask() would retrieve for the given scope."""
    status_filter = "status != 'archived'" if include_all else "status IN ('saved', 'read')"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT id FROM articles WHERE {status_filter} AND embedding IS NOT NULL"
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
    embedding = _pack([0.1] * 10)
    with connect(db_path) as conn:
        for i in range(1, 8):  # 7 saved/read articles — above MIN_ARTICLES=5
            conn.execute(
                """
                INSERT INTO articles(
                    id, url, canonical_url, title, source_slug, source_name,
                    category, kind, status, importance_score, summary, reason,
                    tags, embedding
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    embedding = _pack([0.1] * 10)
    # Insert 6 articles with status 'new' — not picked up by default scope
    with connect(db_path) as conn:
        for i in range(1, 7):
            conn.execute(
                """
                INSERT INTO articles(
                    id, url, canonical_url, title, source_slug, source_name,
                    category, kind, status, importance_score, summary, reason,
                    tags, embedding
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


def _seed_user(db_path: Path, username: str) -> int:
    """Insert a user and return the generated id."""
    with connect(db_path) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'x') RETURNING id",
            (username,),
        ).fetchone()
    return int(row["id"])


def _seed_article_with_embedding(
    db_path: Path,
    article_id: int,
    source_slug: str = "test-source",
    source_name: str = "TestSource",
    legacy_status: str = "new",
) -> None:
    embedding = _pack([0.1] * 10)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO articles(
                id, url, canonical_url, title, source_slug, source_name,
                category, kind, status, importance_score, summary, reason,
                tags, embedding
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


def _set_user_article_state(db_path: Path, user_id: int, article_id: int, state: str) -> None:
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
