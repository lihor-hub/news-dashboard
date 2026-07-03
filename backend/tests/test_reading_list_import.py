"""Tests for the Pocket/Instapaper/Omnivore reading-list import endpoint."""

from __future__ import annotations

from collections.abc import Generator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from news_dashboard.db import connect, init_db
from news_dashboard.main import app
from news_dashboard.reading_list_import import (
    ReadingListImportError,
    parse_instapaper_csv,
    parse_omnivore_json,
    parse_pocket_csv,
    parse_pocket_html,
)


@pytest.fixture
def client(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, is_admin)"
            " VALUES (1, 'reader', 'x', FALSE)"
        )
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client


# ── Unit tests: parsers ────────────────────────────────────────────────────────


def test_parse_pocket_csv_basic() -> None:
    csv_text = (
        "title,url,time_added,tags,status\nMy Article,https://a.com/1,1700000000,tech|rust,unread\n"
    )
    items = parse_pocket_csv(csv_text)
    assert len(items) == 1
    assert items[0].url == "https://a.com/1"
    assert items[0].title == "My Article"
    assert items[0].tags == ["tech", "rust"]
    assert items[0].saved_at is not None


def test_parse_pocket_csv_missing_url_column_raises() -> None:
    with pytest.raises(ReadingListImportError):
        parse_pocket_csv("title,tags\nNo URL,tech\n")


def test_parse_pocket_html_basic() -> None:
    html = (
        "<ul>"
        '<li><a href="https://a.com/1" time_added="1700000000" tags="tech,rust">'
        "Article One</a></li>"
        '<li><a href="https://b.com/2">Article Two</a></li>'
        "</ul>"
    )
    items = parse_pocket_html(html)
    assert len(items) == 2
    assert items[0].url == "https://a.com/1"
    assert items[0].tags == ["tech", "rust"]
    assert items[1].title == "Article Two"
    assert items[1].tags == []


def test_parse_instapaper_csv_basic() -> None:
    csv_text = "URL,Title,Selection,Folder\nhttps://c.com/1,Some Title,,Reading\n"
    items = parse_instapaper_csv(csv_text)
    assert len(items) == 1
    assert items[0].url == "https://c.com/1"
    assert items[0].title == "Some Title"
    assert items[0].tags == ["Reading"]


def test_parse_omnivore_json_basic() -> None:
    json_text = (
        '[{"url": "https://d.com/1", "title": "D Title", "savedAt": "2026-01-01T00:00:00Z", '
        '"labels": [{"name": "ai"}, "python"]}]'
    )
    items = parse_omnivore_json(json_text)
    assert len(items) == 1
    assert items[0].url == "https://d.com/1"
    assert items[0].tags == ["ai", "python"]


def test_parse_omnivore_json_invalid_raises() -> None:
    with pytest.raises(ReadingListImportError):
        parse_omnivore_json("not json at all")


# ── Integration tests: import endpoint ─────────────────────────────────────────


POCKET_CSV = (
    "title,url,time_added,tags,status\n"
    "Article One,https://example.com/one,1700000000,tech|rust,unread\n"
    "Article Two,https://example.com/two,1700000100,,unread\n"
)

INSTAPAPER_CSV = "URL,Title,Selection,Folder\nhttps://example.com/three,Article Three,,Unread\n"

OMNIVORE_JSON = (
    '[{"url": "https://example.com/four", "title": "Article Four", '
    '"savedAt": "2026-01-01T00:00:00Z", "labels": [{"name": "ai"}]}]'
)


def test_import_pocket_csv_creates_saved_articles(client: TestClient, pg_clean: str) -> None:
    response = client.post(
        "/api/reading-list/import",
        data={"service": "pocket"},
        files={"file": ("pocket.csv", BytesIO(POCKET_CSV.encode()), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["added"]) == 2
    assert data["skipped"] == []
    assert data["failed"] == []
    assert data["truncated"] is False

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT a.id, uas.state FROM articles a"
            " JOIN user_article_state uas ON uas.article_id = a.id"
            " WHERE a.url = %s AND uas.user_id = 1",
            ("https://example.com/one",),
        ).fetchone()
        assert row is not None
        assert row["state"] == "later"

        tags = conn.execute(
            "SELECT t.name FROM article_tags at JOIN user_tags t ON t.id = at.tag_id"
            " JOIN articles a ON a.id = at.article_id"
            " WHERE a.url = %s AND at.user_id = 1",
            ("https://example.com/one",),
        ).fetchall()
        tag_names = {r["name"] for r in tags}
        assert tag_names == {"tech", "rust"}


def test_import_instapaper_csv_creates_saved_article(client: TestClient, pg_clean: str) -> None:
    response = client.post(
        "/api/reading-list/import",
        data={"service": "instapaper"},
        files={"file": ("instapaper.csv", BytesIO(INSTAPAPER_CSV.encode()), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["added"]) == 1
    assert data["added"][0]["url"] == "https://example.com/three"


def test_import_omnivore_json_creates_saved_article(client: TestClient, pg_clean: str) -> None:
    response = client.post(
        "/api/reading-list/import",
        data={"service": "omnivore"},
        files={"file": ("omnivore.json", BytesIO(OMNIVORE_JSON.encode()), "application/json")},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["added"]) == 1
    assert data["added"][0]["url"] == "https://example.com/four"


def test_reimporting_same_file_skips_duplicates(client: TestClient, pg_clean: str) -> None:
    first = client.post(
        "/api/reading-list/import",
        data={"service": "pocket"},
        files={"file": ("pocket.csv", BytesIO(POCKET_CSV.encode()), "text/csv")},
    )
    assert first.status_code == 200
    assert len(first.json()["added"]) == 2

    second = client.post(
        "/api/reading-list/import",
        data={"service": "pocket"},
        files={"file": ("pocket.csv", BytesIO(POCKET_CSV.encode()), "text/csv")},
    )
    assert second.status_code == 200
    data = second.json()
    assert data["added"] == []
    assert len(data["skipped"]) == 2
    assert all(item["reason"] == "duplicate" for item in data["skipped"])

    with connect(database_url=pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE url = %s",
            ("https://example.com/one",),
        ).fetchone()
        assert count["n"] == 1


def test_import_rejects_malformed_csv(client: TestClient, pg_clean: str) -> None:
    response = client.post(
        "/api/reading-list/import",
        data={"service": "pocket"},
        files={"file": ("bad.csv", BytesIO(b"not,the,right,columns\n1,2,3,4\n"), "text/csv")},
    )
    assert response.status_code == 400
    assert "url" in response.json()["detail"].lower()


def test_import_rejects_unsupported_service(client: TestClient, pg_clean: str) -> None:
    response = client.post(
        "/api/reading-list/import",
        data={"service": "readwise"},
        files={"file": ("f.csv", BytesIO(b"url\nhttps://a.com\n"), "text/csv")},
    )
    assert response.status_code == 400
