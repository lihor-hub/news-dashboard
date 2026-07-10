"""Tests for #777 — preview a private source before saving it."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import news_dashboard.ingest.service as ingest_module
from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.ingest.service import FeedFetchError, sync_sources


def _make_user(db_path: Path | str, username: str = "alice") -> int:
    user = create_user(username, "pw", db_path=db_path)
    return int(user["id"])


def _api_client(db_path: Path | str, user_id: int) -> Any:
    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    fake = {"id": user_id, "username": "testuser", "email": None, "is_admin": False}

    @contextmanager
    def _ctx() -> Generator[TestClient]:
        app.dependency_overrides[require_auth] = lambda: fake
        try:
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c
        finally:
            app.dependency_overrides.pop(require_auth, None)

    return _ctx()


def test_api_preview_source_returns_entries(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    fake_entries = [
        {"url": "https://example.com/a", "title": "Post A", "description": "", "date": None},
        {"url": "https://example.com/b", "title": "Post B", "description": "", "date": None},
    ]
    monkeypatch.setattr(ingest_module, "_parse_feed_url", lambda _url: fake_entries)

    with _api_client(pg_clean, uid) as client:
        resp = client.post(
            "/api/sources/preview",
            json={"url": "https://example.com/feed.xml", "kind": "rss_feed"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 2
    assert [i["title"] for i in data["items"]] == ["Post A", "Post B"]


def test_api_preview_source_caps_returned_items(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    fake_entries = [
        {"url": f"https://example.com/{i}", "title": f"Post {i}", "description": "", "date": None}
        for i in range(20)
    ]
    monkeypatch.setattr(ingest_module, "_parse_feed_url", lambda _url: fake_entries)

    with _api_client(pg_clean, uid) as client:
        resp = client.post(
            "/api/sources/preview",
            json={"url": "https://example.com/feed.xml", "kind": "rss_feed"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 20
    assert len(data["items"]) == 5


def test_api_preview_source_empty_feed(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    monkeypatch.setattr(ingest_module, "_parse_feed_url", lambda _url: [])

    with _api_client(pg_clean, uid) as client:
        resp = client.post(
            "/api/sources/preview",
            json={"url": "https://example.com/empty.xml", "kind": "rss_feed"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 0
    assert data["items"] == []


def test_api_preview_source_unreachable_feed_returns_422(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    def _boom(_url: str) -> list[dict[str, Any]]:
        msg = "Feed parse failed: not a feed"
        raise FeedFetchError(msg)

    monkeypatch.setattr(ingest_module, "_parse_feed_url", _boom)

    with _api_client(pg_clean, uid) as client:
        resp = client.post(
            "/api/sources/preview",
            json={"url": "https://example.com/broken.xml", "kind": "rss_feed"},
        )

    assert resp.status_code == 422
    assert "Feed parse failed" in resp.json()["detail"]


def test_api_preview_source_rejects_unsupported_kind(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
        resp = client.post(
            "/api/sources/preview",
            json={"url": "https://example.com/scraped", "kind": "scraped_page"},
        )

    assert resp.status_code == 400
    assert "unsupported source kind 'scraped_page'" in resp.json()["detail"]


def test_api_preview_source_rejects_unsafe_url(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
        resp = client.post(
            "/api/sources/preview",
            json={"url": "http://127.0.0.1/admin", "kind": "rss_feed"},
        )

    assert resp.status_code == 400
    assert "unsafe" in resp.json()["detail"]


def test_api_preview_source_does_not_persist_source_or_articles(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    fake_entries = [
        {"url": "https://example.com/a", "title": "Post A", "description": "", "date": None},
    ]
    monkeypatch.setattr(ingest_module, "_parse_feed_url", lambda _url: fake_entries)

    with _api_client(pg_clean, uid) as client:
        resp = client.post(
            "/api/sources/preview",
            json={"url": "https://example.com/feed.xml", "kind": "rss_feed"},
        )
    assert resp.status_code == 200

    with connect(pg_clean) as conn:
        source_row = conn.execute(
            "SELECT 1 FROM sources WHERE url = %s", ("https://example.com/feed.xml",)
        ).fetchone()
        article_row = conn.execute(
            "SELECT 1 FROM articles WHERE url = %s", ("https://example.com/a",)
        ).fetchone()
    assert source_row is None
    assert article_row is None
