"""Tests for article body fetch and caching (issue #79)."""

from __future__ import annotations

import http.server
import threading
from pathlib import Path
from unittest.mock import patch

from news_dashboard.body_fetch import (
    extract_body,
    fetch_and_cache_body,
    get_article,
    prefetch_article_bodies,
)
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

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
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
            "UPDATE articles SET url=%s, canonical_url=%s WHERE id=%s",
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
            "UPDATE articles SET body='cached text', body_status='ok' WHERE id=%s",
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


# ── get_article with user_id ──────────────────────────────────────────────────


def _seed_user(db_path: Path, username: str = "alice") -> int:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO users(username, password_hash, is_admin)
            VALUES (%s, 'x', FALSE)
            ON CONFLICT(username) DO NOTHING
            """,
            (username,),
        )
        row = conn.execute("SELECT id FROM users WHERE username=%s", (username,)).fetchone()
    return int(row["id"] if isinstance(row, dict) else row[0])


def test_get_article_with_no_uas_defaults_to_today(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)
    user_id = _seed_user(db_path)
    result = get_article(article_id, db_path=db_path, user_id=user_id)
    assert result is not None
    assert result["state"] == "today"
    assert result["starred"] is False
    assert result["done_at"] is None


def test_get_article_with_uas_returns_user_state(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)
    user_id = _seed_user(db_path)

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_article_state(user_id, article_id, state, starred, done_at)
            VALUES (%s, %s, 'done', TRUE, '2024-06-01T12:00:00')
            """,
            (user_id, article_id),
        )

    result = get_article(article_id, db_path=db_path, user_id=user_id)
    assert result is not None
    assert result["state"] == "done"
    assert result["starred"] is True
    done_at = result["done_at"]
    done_at_str = done_at.isoformat() if hasattr(done_at, "isoformat") else str(done_at)
    assert done_at_str.startswith("2024-06-01T12:00")


def test_get_article_with_user_id_does_not_bleed_across_users(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)
    user_a = _seed_user(db_path, "alice")
    user_b = _seed_user(db_path, "bob")

    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, state, starred)"
            " VALUES (%s, %s, 'done', TRUE)",
            (user_a, article_id),
        )

    result_b = get_article(article_id, db_path=db_path, user_id=user_b)
    assert result_b is not None
    assert result_b["state"] == "today"
    assert result_b["starred"] is False


# ── fetch_and_cache_body with user_id ────────────────────────────────────────


def test_fetch_and_cache_body_with_user_id_reflects_state(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)
    user_id = _seed_user(db_path)

    with connect(db_path) as conn:
        conn.execute(
            "UPDATE articles SET body='cached', body_status='ok' WHERE id=%s",
            (article_id,),
        )
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, state, starred)"
            " VALUES (%s, %s, 'done', TRUE)",
            (user_id, article_id),
        )

    result = fetch_and_cache_body(article_id, db_path=db_path, user_id=user_id)
    assert result is not None
    assert result["body_status"] == "ok"
    assert result["state"] == "done"
    assert result["starred"] is True


# ── prefetch_article_bodies ───────────────────────────────────────────────────


def test_prefetch_article_bodies_returns_zero_when_none_missing(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    init_db(db_path)
    assert prefetch_article_bodies(db_path=db_path) == 0


def test_prefetch_article_bodies_fetches_missing(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)

    html = b"""
    <html><body>
      <p>Prefetch test paragraph that is long enough to be extracted by the parser.</p>
      <p>Another paragraph with enough content to make it past the forty-char minimum.</p>
    </body></html>
    """
    url, thread = _start_server(html)

    with connect(db_path) as conn:
        conn.execute(
            "UPDATE articles SET url=%s, canonical_url=%s, body_status='missing' WHERE id=%s",
            (url, url, article_id),
        )

    count = prefetch_article_bodies(db_path=db_path)
    thread.join(timeout=2)

    assert count == 1

    with connect(db_path) as conn:
        row = conn.execute("SELECT body_status FROM articles WHERE id=%s", (article_id,)).fetchone()
    status = row["body_status"] if isinstance(row, dict) else row[0]
    assert status == "ok"


def test_prefetch_article_bodies_skips_already_ok(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)

    with connect(db_path) as conn:
        conn.execute(
            "UPDATE articles SET body='already here', body_status='ok' WHERE id=%s",
            (article_id,),
        )

    called: list[str] = []

    def fake_extract(url: str) -> tuple[str, str]:
        called.append(url)
        return "new", "ok"

    with patch("news_dashboard.body_fetch.extract_body", fake_extract):
        count = prefetch_article_bodies(db_path=db_path)

    assert count == 0
    assert called == [], "should not re-fetch articles that already have a body"


# ── _ai_extract_body ──────────────────────────────────────────────────────────


def test_ai_extract_body_skipped_without_api_key(tmp_path: Path) -> None:
    from news_dashboard.body_fetch import _ai_extract_body

    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("OPENAI_API_KEY", None)
        body, status = _ai_extract_body("https://example.com/article")

    assert status == "error"
    assert body == ""


def test_ai_extract_body_calls_openai_on_html(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from news_dashboard.body_fetch import _ai_extract_body

    mock_resp = MagicMock()
    mock_resp.text = "<html><body>Hello world</body></html>"

    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "Hello world"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("httpx.get", return_value=mock_resp),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        body, status = _ai_extract_body("https://example.com/article")

    assert status == "ok"
    assert body == "Hello world"
    mock_client.chat.completions.create.assert_called_once()


def test_ai_extract_body_returns_error_on_http_failure(tmp_path: Path) -> None:
    from news_dashboard.body_fetch import _ai_extract_body

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("httpx.get", side_effect=RuntimeError("connection refused")),
    ):
        body, status = _ai_extract_body("https://example.com/article")

    assert status == "error"
    assert body == ""


def test_ai_extract_body_returns_error_when_openai_returns_empty(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from news_dashboard.body_fetch import _ai_extract_body

    mock_resp = MagicMock()
    mock_resp.text = "<html><body>some html</body></html>"

    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "   "
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("httpx.get", return_value=mock_resp),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        body, status = _ai_extract_body("https://example.com/article")

    assert status == "error"
    assert body == ""


def test_ai_extract_body_truncates_html_to_limit(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from news_dashboard.body_fetch import _AI_HTML_LIMIT, _AI_PROMPT, _ai_extract_body

    # 'A' * limit + 'B' * limit — 'B' must never appear in the OpenAI call
    long_html = "A" * _AI_HTML_LIMIT + "B" * _AI_HTML_LIMIT
    mock_resp = MagicMock()
    mock_resp.text = long_html

    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "extracted"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("httpx.get", return_value=mock_resp),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        _ai_extract_body("https://example.com/article")

    mock_client.chat.completions.create.assert_called_once()
    # call_args.kwargs["messages"] is a list[dict]; inspect the sent content
    sent_messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
    assert isinstance(sent_messages, list)
    assert len(sent_messages) == 1
    prompt_msg = sent_messages[0]["content"]
    assert isinstance(prompt_msg, str)
    # The 'B' portion (beyond the limit) must not appear in the sent message
    assert "B" not in prompt_msg
    # The 'A' portion (within the limit) must be present
    assert "A" * 10 in prompt_msg
    # Exact length: prompt + '\n\n' + truncated html
    assert len(prompt_msg) == len(_AI_PROMPT) + 2 + _AI_HTML_LIMIT


# ── fetch_and_cache_body with AI fallback ─────────────────────────────────────


def test_fetch_and_cache_body_uses_ai_fallback_when_scraper_fails(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)

    with (
        patch("news_dashboard.body_fetch.extract_body", return_value=("", "error")),
        patch(
            "news_dashboard.body_fetch._ai_extract_body",
            return_value=("AI extracted text", "ok"),
        ),
    ):
        result = fetch_and_cache_body(article_id, db_path=db_path)

    assert result is not None
    assert result["body_status"] == "ok"
    assert result["body"] == "AI extracted text"


def test_fetch_and_cache_body_ai_fallback_not_called_when_scraper_ok(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)
    ai_calls: list[str] = []

    def fake_ai(url: str, *, user_id: int | None = None) -> tuple[str, str]:
        ai_calls.append(url)
        return "ai text", "ok"

    with (
        patch("news_dashboard.body_fetch.extract_body", return_value=("scraper text", "ok")),
        patch("news_dashboard.body_fetch._ai_extract_body", side_effect=fake_ai),
    ):
        result = fetch_and_cache_body(article_id, db_path=db_path)

    assert result is not None
    assert result["body_status"] == "ok"
    assert result["body"] == "scraper text"
    assert ai_calls == [], "AI fallback must not run when scraper succeeds"


def test_fetch_and_cache_body_ai_fallback_result_is_cached(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    article_id = _seed_article(db_path)
    ai_calls: list[str] = []

    def fake_ai(url: str, *, user_id: int | None = None) -> tuple[str, str]:
        ai_calls.append(url)
        return "AI body text", "ok"

    with (
        patch("news_dashboard.body_fetch.extract_body", return_value=("", "error")),
        patch("news_dashboard.body_fetch._ai_extract_body", side_effect=fake_ai),
    ):
        result1 = fetch_and_cache_body(article_id, db_path=db_path)
        result2 = fetch_and_cache_body(article_id, db_path=db_path)

    assert result1 is not None
    assert result2 is not None
    assert result1["body"] == "AI body text"
    assert result2["body"] == "AI body text"
    assert len(ai_calls) == 1, "AI fallback must be called only once; second call uses cache"
