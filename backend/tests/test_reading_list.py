"""Tests for the Reading List feature: save ad-hoc links, background
metadata fetch, prioritization, and mark-as-done.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import ANY, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from news_dashboard.ai_client import ManagedPrompt
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


def test_archive_and_restore_item_via_api(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    monkeypatch.setattr(service, "fetch_metadata_for_item", lambda _item_id: None)

    try:
        with _client_for(user_id) as client:
            item = client.post("/api/reading-list", json={"url": "https://example.com/1"}).json()

            archived = client.patch(f"/api/reading-list/{item['id']}", json={"status": "archived"})
            assert archived.status_code == 200
            assert archived.json()["status"] == "archived"

            unread = client.get("/api/reading-list?status=unread").json()["items"]
            assert unread == []
            archived_list = client.get("/api/reading-list?status=archived").json()["items"]
            assert [entry["id"] for entry in archived_list] == [item["id"]]

            restored = client.patch(f"/api/reading-list/{item['id']}", json={"status": "unread"})
            assert restored.status_code == 200
            assert restored.json()["status"] == "unread"

            archived_list_after_restore = client.get("/api/reading-list?status=archived").json()[
                "items"
            ]
            assert archived_list_after_restore == []
            unread_after_restore = client.get("/api/reading-list?status=unread").json()["items"]
            assert [entry["id"] for entry in unread_after_restore] == [item["id"]]
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_list_items_filters_by_text_kind_status_and_user(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    alice = _make_user(database_url, "alice")
    bob = _make_user(database_url, "bob")

    article = service.add_item(
        alice, "https://example.com/briefing", note="weekly market notes", database_url=database_url
    )
    video = service.add_item(
        alice, "https://www.youtube.com/watch?v=abc", database_url=database_url
    )
    bob_item = service.add_item(bob, "https://example.com/private", database_url=database_url)
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            UPDATE reading_list_items
            SET title = %s, description = %s, site_name = %s
            WHERE id = %s
            """,
            ("Market briefing", "Energy equities recap", "Desk", article["id"]),
        )
        conn.execute(
            """
            UPDATE reading_list_items
            SET title = %s, description = %s, site_name = %s, status = 'done'
            WHERE id = %s
            """,
            ("Launch video", "Product walkthrough", "YouTube", video["id"]),
        )
        conn.execute(
            "UPDATE reading_list_items SET title = %s WHERE id = %s",
            ("Market private", bob_item["id"]),
        )

    text_matches = service.list_items(alice, q="market", database_url=database_url)
    assert [item["id"] for item in text_matches] == [article["id"]]

    video_matches = service.list_items(alice, kind="video", database_url=database_url)
    assert [item["id"] for item in video_matches] == [video["id"]]

    combined = service.list_items(
        alice, status="done", q="walkthrough", kind="video", database_url=database_url
    )
    assert [item["id"] for item in combined] == [video["id"]]


def test_list_endpoint_validates_kind(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)

    try:
        with _client_for(user_id) as client:
            response = client.get("/api/reading-list?kind=podcast")
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 422


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


# ── AI summary generation (Postgres) ─────────────────────────────────────────


def test_generate_summary_for_item_success(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    item = service.add_item(user_id, "https://example.com/post", database_url=database_url)
    with connect(database_url=database_url) as conn:
        conn.execute(
            "UPDATE reading_list_items SET title = %s, description = %s WHERE id = %s",
            ("A great post", "It explains things", item["id"]),
        )

    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "A concise take on why this post matters."
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion
    managed_prompt = ManagedPrompt(text="compiled prompt for A great post")

    with (
        patch.dict("os.environ", {"FREE_LLM_API_KEY": "test-key"}),
        patch("openai.OpenAI", return_value=mock_client),
        patch("news_dashboard.ai_client.chat_create", return_value=mock_completion) as chat_create,
        patch("news_dashboard.ai_client.get_prompt", return_value=managed_prompt) as get_prompt,
    ):
        service.generate_summary_for_item(item["id"], database_url=database_url)

    items = service.list_items(user_id, database_url=database_url)
    assert items[0]["summary_status"] == "ok"
    assert items[0]["summary"] == "A concise take on why this post matters."
    call_kwargs = chat_create.call_args.kwargs
    assert "A great post" in call_kwargs["messages"][0]["content"]
    get_prompt.assert_called_once_with(
        "reading-list-summary",
        fallback=ANY,
        label="production",
        prompt_type="text",
        variables={"reading_list_text": "Title: A great post\nDescription: It explains things"},
    )
    assert chat_create.call_args.kwargs["prompt"] is managed_prompt


def test_generate_summary_for_item_records_error_on_ai_failure(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    item = service.add_item(user_id, "https://example.com/post", database_url=database_url)
    with connect(database_url=database_url) as conn:
        conn.execute(
            "UPDATE reading_list_items SET title = %s, description = %s WHERE id = %s",
            ("A great post", "It explains things", item["id"]),
        )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("upstream 429")

    with (
        patch.dict("os.environ", {"FREE_LLM_API_KEY": "test-key"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        service.generate_summary_for_item(item["id"], database_url=database_url)

    items = service.list_items(user_id, database_url=database_url)
    assert items[0]["summary_status"] == "error"
    assert items[0]["summary"] is None


def test_generate_summary_for_item_skipped_without_ai_credentials(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    item = service.add_item(user_id, "https://example.com/post", database_url=database_url)
    with connect(database_url=database_url) as conn:
        conn.execute(
            "UPDATE reading_list_items SET title = %s, description = %s WHERE id = %s",
            ("A great post", "It explains things", item["id"]),
        )
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    service.generate_summary_for_item(item["id"], database_url=database_url)

    items = service.list_items(user_id, database_url=database_url)
    assert items[0]["summary_status"] == "skipped"
    assert items[0]["summary"] is None


def test_generate_summary_for_item_skipped_without_title_or_description(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    item = service.add_item(user_id, "https://example.com/post", database_url=database_url)

    service.generate_summary_for_item(item["id"], database_url=database_url)

    items = service.list_items(user_id, database_url=database_url)
    assert items[0]["summary_status"] == "skipped"


def test_fetch_metadata_for_item_chains_summary_generation(
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
            "image_url": None,
            "site_name": None,
            "kind": "article",
        },
    )
    captured: dict[str, int] = {}
    monkeypatch.setattr(
        service,
        "generate_summary_for_item",
        lambda item_id, **_kwargs: captured.setdefault("item_id", item_id),
    )

    service.fetch_metadata_for_item(item["id"], database_url=database_url)

    assert captured["item_id"] == item["id"]


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
