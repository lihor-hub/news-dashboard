"""Tests for article body fetch and caching (issue #79)."""

from __future__ import annotations

import http.server
import threading
from pathlib import Path
from unittest.mock import patch

from news_dashboard.body_fetch import extract_body, fetch_and_cache_body, get_article
from news_dashboard.db import connect, init_db
from news_dashboard.ingest import sync_sources


def _db(tmp_path: Path) -> Path:
    return tmp_path / "news.db"


def _seed_article(db_path: Path) -> int:
    sync_sources(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name, category, kind
            )
            VALUES (
              'https://example.com/article-1', 'https://example.com/article-1',
              'Test Article', 'python-insider', 'Python Insider', 'python', 'rss_feed'
            )
            """
        )
        row = conn.execute(
            "SELECT id FROM articles WHERE url='https://example.com/article-1'"
        ).fetchone()
    return int(row["id"] if isinstance(row, dict) else row[0])


class _SimpleHTTPHandler(http.server.BaseHTTPRequestHandler):
    html = b""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(self.__class__.html)

    def log_message(self, *args: object) -> None:
        pass


def _start_server(html: bytes) -> tuple[str, threading.Thread]:
    _SimpleHTTPHandler.html = html
    server = http.server.HTTPServer(("127.0.0.1", 0), _SimpleHTTPHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.handle_request)
    thread.daemon = True
    thread.start()
    return f"http://127.0.0.1:{port}/", thread


# ── extract_body ──────────────────────────────────────────────────────────────


def test_extract_body_ok() -> None:
    html = b"""
    <html><body>
      <nav>skip nav</nav>
      <main>
        <p>This is a long enough paragraph that should be extracted by the body parser.</p>
        <p>Another paragraph with sufficient content to pass the forty-char filter.</p>
      </main>
      <footer>skip footer</footer>
    </body></html>
    """
    url, thread = _start_server(html)
    body, status = extract_body(url)
    thread.join(timeout=2)
    assert status == "ok"
    assert "long enough paragraph" in body
    assert "skip nav" not in body
    assert "skip footer" not in body


def test_extract_body_error_on_network_failure() -> None:
    body, status = extract_body("http://127.0.0.1:1/")
    assert status == "error"
    assert body == ""


def test_extract_body_rejects_non_http() -> None:
    _body, status = extract_body("file:///etc/passwd")
    assert status == "error"


def test_extract_body_empty_page_returns_error() -> None:
    url, thread = _start_server(b"<html><body></body></html>")
    _body, status = extract_body(url)
    thread.join(timeout=2)
    assert status == "error"


# ── fetch_and_cache_body ──────────────────────────────────────────────────────


def test_fetch_and_cache_body_success(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)

    html = b"""
    <html><body>
      <p>This article body has enough text content to be considered valid extraction.</p>
      <p>Second paragraph with more meaningful content for the reader experience.</p>
    </body></html>
    """
    url, thread = _start_server(html)

    with connect(db_path) as conn:
        conn.execute(
            "UPDATE articles SET url=?, canonical_url=? WHERE id=?",
            (url, url, article_id),
        )

    result = fetch_and_cache_body(article_id, db_path=db_path)
    thread.join(timeout=2)

    assert result is not None
    assert result["body_status"] == "ok"
    assert result["body"] is not None
    assert "enough text content" in result["body"]


def test_fetch_and_cache_body_cache_hit(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)

    with connect(db_path) as conn:
        conn.execute(
            "UPDATE articles SET body='cached text', body_status='ok' WHERE id=?",
            (article_id,),
        )

    called: list[str] = []

    def fake_extract(url: str) -> tuple[str, str]:
        called.append(url)
        return "new text", "ok"

    with patch("news_dashboard.body_fetch.extract_body", fake_extract):
        result = fetch_and_cache_body(article_id, db_path=db_path)

    assert called == [], "should not re-fetch when cache is warm"
    assert result is not None
    assert result["body"] == "cached text"


def test_fetch_and_cache_body_fetch_error(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)

    with patch("news_dashboard.body_fetch.extract_body", return_value=("", "error")):
        result = fetch_and_cache_body(article_id, db_path=db_path)

    assert result is not None
    assert result["body_status"] == "error"
    assert result["body"] is None


def test_fetch_and_cache_body_not_found(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    init_db(db_path)
    result = fetch_and_cache_body(99999, db_path=db_path)
    assert result is None


# ── get_article ───────────────────────────────────────────────────────────────


def test_get_article_returns_article(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)
    result = get_article(article_id, db_path=db_path)
    assert result is not None
    assert result["id"] == article_id
    assert result["title"] == "Test Article"
    assert "embedding" not in result


def test_get_article_returns_none_for_missing(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    init_db(db_path)
    assert get_article(99999, db_path=db_path) is None
