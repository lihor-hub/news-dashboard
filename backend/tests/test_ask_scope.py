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


def _seed_articles(db_path: Path) -> None:
    """Insert one article per legacy status with a pre-set embedding."""
    init_db(db_path)
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
