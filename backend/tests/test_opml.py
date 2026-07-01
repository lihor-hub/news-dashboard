"""Tests for OPML import/export endpoints."""

from __future__ import annotations

from collections.abc import Generator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from news_dashboard.db import connect, init_db
from news_dashboard.main import app, _generate_opml


@pytest.fixture
def client(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client


def _seed_sources(database_url: str) -> None:
    """Insert a user and a few RSS sources owned by that user."""
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, is_admin)"
            " VALUES (1, 'reader', 'x', FALSE)"
        )
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)"
            " VALUES ('arxiv', 'ArXiv AI', 'https://arxiv.org/rss/cs.AI', 'ai', 'rss_feed', 50, TRUE, 1)"
        )
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)"
            " VALUES ('hacker-news', 'Hacker News', 'https://news.ycombinator.com/rss', 'tech', 'rss_feed', 80, TRUE, 1)"
        )
        # A non-rss_feed source — should be excluded from OPML export
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)"
            " VALUES ('hn-trending', 'HN Trending', 'https://news.ycombinator.com/trending', 'tech', 'trending_feed', 70, TRUE, 1)"
        )


# ── Unit tests for _generate_opml ─────────────────────────────────────────────


def test_generate_opml_produces_valid_xml() -> None:
    sources = [
        {"name": "Blog A", "url": "https://a.com/feed.xml"},
        {"name": "Blog B", "url": "https://b.com/rss"},
    ]
    xml = _generate_opml(sources)
    assert '<?xml' in xml
    assert '<opml version="2.0">' in xml
    assert 'text="Blog A"' in xml
    assert 'xmlUrl="https://a.com/feed.xml"' in xml
    assert 'text="Blog B"' in xml


def test_generate_opml_empty_sources() -> None:
    xml = _generate_opml([])
    assert '<?xml' in xml
    assert '<body />' in xml  # body tag is self-closed when empty


def test_generate_opml_includes_html_url() -> None:
    sources = [
        {"name": "Blog", "url": "https://blog.com/feed", "html_url": "https://blog.com"},
    ]
    xml = _generate_opml(sources)
    assert 'htmlUrl="https://blog.com"' in xml


# ── Integration tests for export endpoint ──────────────────────────────────────


def test_export_opml_returns_opml_document(client: TestClient, pg_clean: str) -> None:
    _seed_sources(pg_clean)
    response = client.get("/api/sources/export.opml")
    assert response.status_code == 200
    assert "text/x-opml" in response.headers["content-type"]
    body = response.text
    assert "<opml" in body
    # Should include the two rss_feed sources but not the trending_feed
    assert "ArXiv AI" in body
    assert "Hacker News" in body
    assert "trending" not in body.lower().replace("trending_feed", "")
    # Round-trip: exported OPML should be parseable
    import xml.etree.ElementTree as ET

    root = ET.fromstring(body)
    outlines = root.findall(".//outline")
    xml_urls = [o.get("xmlUrl") for o in outlines if o.get("xmlUrl")]
    assert "https://arxiv.org/rss/cs.AI" in xml_urls
    assert "https://news.ycombinator.com/rss" in xml_urls


def test_export_opml_empty(client: TestClient, pg_clean: str) -> None:
    init_db(database_url=pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, is_admin)"
            " VALUES (1, 'reader', 'x', FALSE)"
        )
    response = client.get("/api/sources/export.opml")
    assert response.status_code == 200
    body = response.text
    assert "<opml" in body


# ── Integration tests for import endpoint ──────────────────────────────────────


OPML_VALID = """\
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>Test Subscriptions</title>
  </head>
  <body>
    <outline type="rss" text="New Feed" xmlUrl="https://new-blog.com/feed.xml" />
    <outline type="rss" text="Another Feed" xmlUrl="https://another.com/rss" />
  </body>
</opml>
"""

OPML_INVALID = "<not-opml-at-all"


def test_import_opml_adds_sources(client: TestClient, pg_clean: str) -> None:
    init_db(database_url=pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, is_admin)"
            " VALUES (1, 'reader', 'x', FALSE)"
        )
    response = client.post(
        "/api/sources/import",
        files={"file": ("subs.opml", BytesIO(OPML_VALID.encode()), "application/xml")},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["added"]) == 2
    assert len(data["skipped"]) == 0
    assert len(data["failed"]) == 0


def test_import_opml_skips_duplicates(client: TestClient, pg_clean: str) -> None:
    _seed_sources(pg_clean)
    # Import an OPML that contains a URL already owned by the user
    opml_dup = """\
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Dup</title></head>
  <body>
    <outline type="rss" text="ArXiv AI" xmlUrl="https://arxiv.org/rss/cs.AI" />
    <outline type="rss" text="Fresh Feed" xmlUrl="https://fresh.com/rss" />
  </body>
</opml>
"""
    response = client.post(
        "/api/sources/import",
        files={"file": ("dup.opml", BytesIO(opml_dup.encode()), "application/xml")},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["added"]) == 1
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["reason"] == "duplicate"


def test_import_opml_rejects_malformed_xml(client: TestClient, pg_clean: str) -> None:
    init_db(database_url=pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, is_admin)"
            " VALUES (1, 'reader', 'x', FALSE)"
        )
    response = client.post(
        "/api/sources/import",
        files={"file": ("bad.opml", BytesIO(OPML_INVALID.encode()), "application/xml")},
    )
    assert response.status_code == 400
    assert "Invalid OPML" in response.json()["detail"]


def test_import_opml_skips_outlines_without_xmlurl(
    client: TestClient, pg_clean: str
) -> None:
    """Folder-level outlines (no xmlUrl) should be silently skipped."""
    init_db(database_url=pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, is_admin)"
            " VALUES (1, 'reader', 'x', FALSE)"
        )
    opml_folders = """\
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Folders</title></head>
  <body>
    <outline text="Tech" />
    <outline type="rss" text="Feed" xmlUrl="https://feed.com/rss" />
  </body>
</opml>
"""
    response = client.post(
        "/api/sources/import",
        files={
            "file": ("folders.opml", BytesIO(opml_folders.encode()), "application/xml")
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["added"]) == 1
    assert data["added"][0]["name"] == "Feed"


def test_export_import_roundtrip(client: TestClient, pg_clean: str) -> None:
    """Export OPML → re-import into a clean state → sources should match."""
    _seed_sources(pg_clean)

    # Export
    export_resp = client.get("/api/sources/export.opml")
    assert export_resp.status_code == 200
    opml_body = export_resp.content

    # Clean sources for re-import (truncate within same user)
    with connect(database_url=pg_clean) as conn:
        conn.execute("DELETE FROM sources WHERE owner_user_id = 1")

    # Re-import
    import_resp = client.post(
        "/api/sources/import",
        files={"file": ("reimport.opml", BytesIO(opml_body), "text/x-opml")},
    )
    assert import_resp.status_code == 200
    data = import_resp.json()
    # Both RSS feeds should reappear
    assert len(data["added"]) == 2
    added_names = {s["name"] for s in data["added"]}
    assert "ArXiv AI" in added_names
    assert "Hacker News" in added_names
