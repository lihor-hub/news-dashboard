"""Regression coverage for rapid article actions without external services."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from typing import Any

import pytest

from news_dashboard import db, embeddings
from news_dashboard.articles import service


def test_lazy_embedding_releases_connection_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = 0
    writes: list[str] = []

    class Connection:
        def execute(self, query: str, _params: Any) -> Connection:
            if query.startswith("UPDATE"):
                writes.append(query)
            return self

        def fetchone(self) -> dict[str, Any]:
            return {
                "id": 1,
                "title": "Title",
                "summary": "Summary",
                "reason": "",
                "tags": "",
                "embedding_vec": None,
            }

    @contextmanager
    def connect(*args: Any, **kwargs: Any) -> Any:
        nonlocal active
        active += 1
        try:
            yield Connection()
        finally:
            active -= 1

    def embed(text: str) -> list[float]:
        assert active == 0, "network calls must not hold a database connection"
        return [0.1, 0.2]

    monkeypatch.setattr(db, "init_db", lambda *_args: None)
    monkeypatch.setattr(db, "connect", connect)
    monkeypatch.setattr(embeddings, "_embed", embed)
    embeddings.ensure_article_embedded(1)
    assert active == 0
    assert len(writes) == 1
    assert "AND embedding_vec IS NULL" in writes[0]


def test_overlapping_done_embeddings_are_coalesced_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = Event()
    release = Event()
    calls: list[int] = []

    def embed(article_id: int) -> None:
        calls.append(article_id)
        entered.set()
        assert release.wait(5)
        message = "optional provider unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(embeddings, "ensure_article_embedded", embed)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.embed_article_background, 123)
        try:
            assert entered.wait(5)
            duplicate = executor.submit(service.embed_article_background, 123)
            duplicate.result(timeout=5)
            assert calls == [123]
        finally:
            release.set()
        first.result(timeout=5)
    service.embed_article_background(123)
    assert calls == [123, 123]
    assert 123 not in service._EMBEDDING_IN_FLIGHT
