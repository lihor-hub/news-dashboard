"""Tests for importing Pocket/Instapaper/Omnivore exports into the reading list."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.main import app
from news_dashboard.reading_list import importers, router, service

POCKET_CSV = (
    "title,url,time_added,tags,status\n"
    "First Post,https://example.com/a,1700000000,tech,unread\n"
    'Archived Post,https://example.com/b,1700000100,"tech,news",archive\n'
)

INSTAPAPER_CSV = (
    "URL,Title,Selection,Folder,Timestamp\n"
    "https://example.com/c,Third Post,,Unread,1700000200\n"
    "https://example.com/d,Fourth Post,,Archive,1700000300\n"
)

OMNIVORE_JSON = """
[
  {"url": "https://example.com/e", "title": "Fifth Post", "labels": [{"name": "reading"}],
   "savedAt": "2023-11-14T00:00:00Z", "state": "SUCCEEDED"},
  {"url": "https://example.com/f", "title": "Sixth Post", "labels": ["archive-tag"],
   "savedAt": "2023-11-15T00:00:00Z", "state": "ARCHIVED"}
]
"""


# ── Parser unit tests ────────────────────────────────────────────────────────


def test_parse_pocket_csv() -> None:
    items = importers.parse_pocket_csv(POCKET_CSV.encode())
    assert [i.url for i in items] == ["https://example.com/a", "https://example.com/b"]
    assert items[0].title == "First Post"
    assert items[0].status == "unread"
    assert items[0].tags == ["tech"]
    assert items[1].status == "archived"
    assert items[1].tags == ["tech", "news"]
    assert items[0].created_at is not None


def test_parse_pocket_csv_requires_url_column() -> None:
    with pytest.raises(importers.ImportParseError):
        importers.parse_pocket_csv(b"title,link\nA,https://example.com\n")


def test_parse_instapaper_csv() -> None:
    items = importers.parse_instapaper_csv(INSTAPAPER_CSV.encode())
    assert [i.url for i in items] == ["https://example.com/c", "https://example.com/d"]
    assert items[0].status == "unread"
    assert items[1].status == "archived"
    assert items[1].title == "Fourth Post"


def test_parse_omnivore_json() -> None:
    items = importers.parse_omnivore_json(OMNIVORE_JSON.encode())
    assert [i.url for i in items] == ["https://example.com/e", "https://example.com/f"]
    assert items[0].status == "unread"
    assert items[0].tags == ["reading"]
    assert items[1].status == "archived"
    assert items[1].tags == ["archive-tag"]


def test_parse_omnivore_json_rejects_malformed_input() -> None:
    with pytest.raises(importers.ImportParseError):
        importers.parse_omnivore_json(b"not json")


def test_parse_omnivore_json_rejects_non_list() -> None:
    with pytest.raises(importers.ImportParseError):
        importers.parse_omnivore_json(b'{"foo": "bar"}')


# ── API integration tests (Postgres) ────────────────────────────────────────


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


def test_import_pocket_creates_saved_items(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)

    try:
        with _client_for(user_id) as client:
            response = client.post(
                "/api/reading-list/import",
                files={"file": ("pocket.csv", POCKET_CSV, "text/csv")},
                data={"source": "pocket"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    body = response.json()
    assert body == {"added": 2, "skipped": 0, "failed": 0}

    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            "SELECT url, title, status, note, fetch_status FROM reading_list_items"
            " WHERE user_id = %s ORDER BY url",
            (user_id,),
        ).fetchall()
    assert len(rows) == 2
    assert rows[0]["url"] == "https://example.com/a"
    assert rows[0]["title"] == "First Post"
    assert rows[0]["status"] == "unread"
    assert rows[0]["fetch_status"] == "ok"
    assert rows[1]["status"] == "archived"
    assert rows[1]["note"] == "Tags: tech, news"


def test_reimport_same_file_skips_duplicates(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)

    try:
        with _client_for(user_id) as client:
            first = client.post(
                "/api/reading-list/import",
                files={"file": ("pocket.csv", POCKET_CSV, "text/csv")},
                data={"source": "pocket"},
            )
            second = client.post(
                "/api/reading-list/import",
                files={"file": ("pocket.csv", POCKET_CSV, "text/csv")},
                data={"source": "pocket"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert first.json() == {"added": 2, "skipped": 0, "failed": 0}
    assert second.json() == {"added": 0, "skipped": 2, "failed": 0}

    with connect(database_url=database_url) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM reading_list_items WHERE user_id = %s",
            (user_id,),
        ).fetchone()["count"]
    assert count == 2


def test_import_instapaper(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)

    try:
        with _client_for(user_id) as client:
            response = client.post(
                "/api/reading-list/import",
                files={"file": ("instapaper.csv", INSTAPAPER_CSV, "text/csv")},
                data={"source": "instapaper"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    assert response.json() == {"added": 2, "skipped": 0, "failed": 0}


def test_import_omnivore(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)

    try:
        with _client_for(user_id) as client:
            response = client.post(
                "/api/reading-list/import",
                files={"file": ("omnivore.json", OMNIVORE_JSON, "application/json")},
                data={"source": "omnivore"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    assert response.json() == {"added": 2, "skipped": 0, "failed": 0}


def test_import_rejects_malformed_file(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)

    try:
        with _client_for(user_id) as client:
            response = client.post(
                "/api/reading-list/import",
                files={"file": ("garbage.json", "not json", "application/json")},
                data={"source": "omnivore"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 400


def test_import_rejects_unknown_source(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)

    try:
        with _client_for(user_id) as client:
            response = client.post(
                "/api/reading-list/import",
                files={"file": ("x.csv", "url\nhttps://example.com\n", "text/csv")},
                data={"source": "readwise"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 400


def test_import_enforces_batch_cap(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    items = [importers.ImportedItem(url=f"https://example.com/{i}") for i in range(3)]

    with pytest.raises(service.ImportTooLargeError):
        service.import_items(user_id, items, max_items=2, database_url=database_url)


def test_import_rejects_oversized_upload(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    monkeypatch.setattr(router, "MAX_IMPORT_BYTES", 100)
    oversized_csv = "url\n" + "\n".join(f"https://example.com/{i}" for i in range(50))
    assert len(oversized_csv) > 100

    try:
        with _client_for(user_id) as client:
            response = client.post(
                "/api/reading-list/import",
                files={"file": ("pocket.csv", oversized_csv, "text/csv")},
                data={"source": "pocket"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 413

    with connect(database_url=database_url) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM reading_list_items WHERE user_id = %s",
            (user_id,),
        ).fetchone()["count"]
    assert count == 0


def test_import_rejects_oversized_content_length_before_parsing(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    monkeypatch.setattr(router, "MAX_IMPORT_BYTES", 100)
    calls: list[bytes] = []

    def _tracking_parser(contents: bytes) -> list[importers.ImportedItem]:
        calls.append(contents)
        return []

    monkeypatch.setattr(router, "PARSERS", {"pocket": _tracking_parser})
    oversized_csv = "url\n" + "\n".join(f"https://example.com/{i}" for i in range(50))

    try:
        with _client_for(user_id) as client:
            response = client.post(
                "/api/reading-list/import",
                files={"file": ("pocket.csv", oversized_csv, "text/csv")},
                data={"source": "pocket"},
                headers={"content-length": str(len(oversized_csv) * 10)},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 413
    assert calls == []


def test_import_under_limit_still_succeeds(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    monkeypatch.setattr(router, "MAX_IMPORT_BYTES", 10_000)

    try:
        with _client_for(user_id) as client:
            response = client.post(
                "/api/reading-list/import",
                files={"file": ("pocket.csv", POCKET_CSV, "text/csv")},
                data={"source": "pocket"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    assert response.json() == {"added": 2, "skipped": 0, "failed": 0}
