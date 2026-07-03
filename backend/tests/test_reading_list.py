"""Tests for the Reading List feature: save ad-hoc links, background
metadata fetch, prioritization, and mark-as-done.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.main import app
from news_dashboard.reading_list import metadata, service

# ── URL normalization ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "HTTPS://Example.com/Post/?utm_source=x&fbclid=y#frag",
            "https://example.com/Post",
        ),
        (
            "https://www.youtube.com/watch?v=abc123&utm_campaign=share",
            "https://www.youtube.com/watch?v=abc123",
        ),
        ("https://example.com", "https://example.com/"),
        ("  https://example.com/a  ", "https://example.com/a"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert service.normalize_url(raw) == expected


# ── Kind detection ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video"),
        ("https://youtu.be/dQw4w9WgXcQ", "video"),
        ("https://www.youtube.com/shorts/abc", "video"),
        ("https://www.youtube.com/@veritasium", "channel"),
        ("https://www.youtube.com/channel/UCabc", "channel"),
        ("https://example.com/blog/post", "article"),
    ],
)
def test_detect_kind(url: str, expected: str) -> None:
    assert metadata.detect_kind(url) == expected


# ── HTML metadata parsing (no network) ───────────────────────────────────────


def test_parse_html_metadata_extracts_opengraph() -> None:
    html = """
    <html><head>
      <title>Fallback title</title>
      <meta property="og:title" content="OG title" />
      <meta property="og:description" content="OG description" />
      <meta property="og:image" content="https://cdn.example.com/img.png" />
      <meta property="og:site_name" content="Example Blog" />
    </head><body></body></html>
    """
    parsed = metadata.parse_html_metadata(html)
    assert parsed["title"] == "OG title"
    assert parsed["description"] == "OG description"
    assert parsed["image_url"] == "https://cdn.example.com/img.png"
    assert parsed["site_name"] == "Example Blog"


def test_parse_html_metadata_falls_back_to_title_and_meta_description() -> None:
    html = """
    <html><head>
      <title>Plain page</title>
      <meta name="description" content="Plain description">
    </head><body></body></html>
    """
    parsed = metadata.parse_html_metadata(html)
    assert parsed["title"] == "Plain page"
    assert parsed["description"] == "Plain description"
    assert parsed["image_url"] is None
    assert parsed["site_name"] is None


def test_fetch_url_metadata_parses_html_page(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <html><head>
      <meta property="og:title" content="A post" />
      <meta property="og:site_name" content="Blog" />
    </head></html>
    """
    monkeypatch.setattr(metadata, "_fetch_html", lambda _url: html)
    result = metadata.fetch_url_metadata("https://example.com/a-post")
    assert result["title"] == "A post"
    assert result["site_name"] == "Blog"
    assert result["kind"] == "article"


def test_fetch_url_metadata_youtube_uses_oembed(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_fetch_json(url: str) -> dict[str, Any]:
        captured["url"] = url
        return {
            "title": "Cool video",
            "author_name": "Some Channel",
            "thumbnail_url": "https://i.ytimg.com/vi/abc/hqdefault.jpg",
        }

    monkeypatch.setattr(metadata, "_fetch_json", fake_fetch_json)
    result = metadata.fetch_url_metadata("https://www.youtube.com/watch?v=abc")
    assert "youtube.com/oembed" in captured["url"]
    assert result["title"] == "Cool video"
    assert result["site_name"] == "YouTube"
    assert result["image_url"] == "https://i.ytimg.com/vi/abc/hqdefault.jpg"
    assert result["kind"] == "video"
    assert result["description"] == "Some Channel"


# ── API tests (Postgres) ─────────────────────────────────────────────────────


def _setup_db(monkeypatch: pytest.MonkeyPatch, pg_url: str) -> str:
    monkeypatch.setenv("DATABASE_URL", pg_url)
    init_db(database_url=pg_url)
    return pg_url


def _make_user(database_url: str, username: str = "alice") -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _client_for(user_id: int) -> TestClient:
    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def _no_network_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Background metadata fetches must never hit the network in tests."""
    monkeypatch.setattr(
        service,
        "fetch_url_metadata",
        lambda url: pytest.fail(f"unexpected network fetch for {url}"),
    )


def test_add_item_creates_pending_and_dedupes(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    monkeypatch.setattr(service, "fetch_metadata_for_item", lambda _item_id: None)

    try:
        with _client_for(user_id) as client:
            first = client.post(
                "/api/reading-list", json={"url": "https://example.com/post?utm_source=x"}
            )
            second = client.post("/api/reading-list", json={"url": "https://example.com/post"})
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert first.status_code == 201
    item = first.json()
    assert item["url"] == "https://example.com/post?utm_source=x"
    assert item["fetch_status"] == "pending"
    assert item["status"] == "unread"

    assert second.status_code == 200
    assert second.json()["id"] == item["id"]

    with connect(database_url=database_url) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM reading_list_items WHERE user_id = %s",
            (user_id,),
        ).fetchone()["count"]
    assert count == 1


def test_add_item_rejects_invalid_url(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)

    try:
        with _client_for(user_id) as client:
            response = client.post("/api/reading-list", json={"url": "ftp://example.com/file"})
            garbage = client.post("/api/reading-list", json={"url": "not a url"})
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 400
    assert garbage.status_code == 400


def test_list_items_scoped_to_user_and_reorder(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    alice = _make_user(database_url, "alice")
    bob = _make_user(database_url, "bob")
    monkeypatch.setattr(service, "fetch_metadata_for_item", lambda _item_id: None)

    try:
        with _client_for(alice) as client:
            first = client.post("/api/reading-list", json={"url": "https://example.com/1"}).json()
            second = client.post("/api/reading-list", json={"url": "https://example.com/2"}).json()
        with _client_for(bob) as client:
            client.post("/api/reading-list", json={"url": "https://example.com/bob"})

        with _client_for(alice) as client:
            listed = client.get("/api/reading-list").json()["items"]
            assert [entry["id"] for entry in listed] == [first["id"], second["id"]]

            reorder = client.post(
                "/api/reading-list/reorder",
                json={"ordered_ids": [second["id"], first["id"]]},
            )
            assert reorder.status_code == 200
            reordered = client.get("/api/reading-list").json()["items"]
            assert [entry["id"] for entry in reordered] == [second["id"], first["id"]]
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_mark_done_sets_done_at_and_status_filter(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    monkeypatch.setattr(service, "fetch_metadata_for_item", lambda _item_id: None)

    try:
        with _client_for(user_id) as client:
            item = client.post("/api/reading-list", json={"url": "https://example.com/1"}).json()
            done = client.patch(f"/api/reading-list/{item['id']}", json={"status": "done"})
            assert done.status_code == 200
            assert done.json()["status"] == "done"
            assert done.json()["done_at"] is not None

            unread = client.get("/api/reading-list?status=unread").json()["items"]
            assert unread == []
            finished = client.get("/api/reading-list?status=done").json()["items"]
            assert [entry["id"] for entry in finished] == [item["id"]]
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_delete_item_enforces_ownership(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    alice = _make_user(database_url, "alice")
    bob = _make_user(database_url, "bob")
    monkeypatch.setattr(service, "fetch_metadata_for_item", lambda _item_id: None)

    try:
        with _client_for(alice) as client:
            item = client.post("/api/reading-list", json={"url": "https://example.com/1"}).json()
        with _client_for(bob) as client:
            forbidden = client.delete(f"/api/reading-list/{item['id']}")
            assert forbidden.status_code == 404
        with _client_for(alice) as client:
            deleted = client.delete(f"/api/reading-list/{item['id']}")
            assert deleted.status_code == 200
            assert client.get("/api/reading-list").json()["items"] == []
    finally:
        app.dependency_overrides.pop(require_auth, None)


# ── Background metadata fetch (Postgres) ─────────────────────────────────────


def test_fetch_metadata_for_item_updates_row(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    item = service.add_item(user_id, "https://example.com/post", database_url=database_url)

    monkeypatch.setattr(
        service,
        "fetch_url_metadata",
        lambda _url: {
            "title": "Fetched title",
            "description": "Fetched description",
            "image_url": "https://cdn.example.com/img.png",
            "site_name": "Example",
            "kind": "article",
        },
    )
    service.fetch_metadata_for_item(item["id"], database_url=database_url)

    items = service.list_items(user_id, database_url=database_url)
    assert items[0]["fetch_status"] == "ok"
    assert items[0]["title"] == "Fetched title"
    assert items[0]["image_url"] == "https://cdn.example.com/img.png"
    assert items[0]["fetched_at"] is not None


def test_fetch_metadata_for_item_records_error(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    item = service.add_item(user_id, "https://example.com/broken", database_url=database_url)

    def boom(url: str) -> dict[str, Any]:
        message = "connection refused"
        raise RuntimeError(message)

    monkeypatch.setattr(service, "fetch_url_metadata", boom)
    service.fetch_metadata_for_item(item["id"], database_url=database_url)

    items = service.list_items(user_id, database_url=database_url)
    assert items[0]["fetch_status"] == "error"
    assert "connection refused" in items[0]["fetch_error"]


def test_process_pending_items_sweeps_pending(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    service.add_item(user_id, "https://example.com/1", database_url=database_url)
    service.add_item(user_id, "https://example.com/2", database_url=database_url)

    monkeypatch.setattr(
        service,
        "fetch_url_metadata",
        lambda url: {
            "title": f"Title for {url}",
            "description": None,
            "image_url": None,
            "site_name": None,
            "kind": "article",
        },
    )
    processed = service.process_pending_items(database_url=database_url)
    assert processed == 2
    items = service.list_items(user_id, database_url=database_url)
    assert {entry["fetch_status"] for entry in items} == {"ok"}
    assert service.process_pending_items(database_url=database_url) == 0


# ── Route registration ───────────────────────────────────────────────────────


def test_reading_list_routes_registered() -> None:
    paths = app.openapi()["paths"]
    assert "post" in paths["/api/reading-list"]
    assert "get" in paths["/api/reading-list"]
    assert "post" in paths["/api/reading-list/reorder"]
    assert "patch" in paths["/api/reading-list/{item_id}"]
    assert "delete" in paths["/api/reading-list/{item_id}"]
