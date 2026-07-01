"""Unit + integration tests for news_dashboard.digest.

Token helpers and HTML/text rendering are pure and run without a database.
SMTP is always mocked. ``send_digest`` is exercised against the live test
Postgres via the ``pg_clean`` fixture.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import psycopg
import pytest
from fastapi.testclient import TestClient

from news_dashboard import digest
from news_dashboard.auth import create_user

# ── Fixtures ──────────────────────────────────────────────────────────────────

_ARTICLES: list[dict[str, Any]] = [
    {
        "id": 1,
        "title": "First Headline",
        "url": "https://example.com/1",
        "source_name": "Example News",
        "summary": "A short summary.",
        "importance_score": 90,
    },
    {
        "id": 2,
        "title": None,
        "url": None,
        "source_name": None,
        "summary": None,
        "importance_score": 0,
    },
]


# ── Token helpers ─────────────────────────────────────────────────────────────


def test_token_roundtrip_verifies() -> None:
    token = digest._make_token(7, 42)
    assert digest.verify_read_token(42, token) == 7


def test_token_secret_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_SECRET", "token-secret")
    monkeypatch.setenv("SESSION_SECRET", "session-secret")
    token = digest._make_token(7, 42)

    monkeypatch.setenv("TOKEN_SECRET", "different-token-secret")
    assert digest.verify_read_token(42, token) is None

    monkeypatch.setenv("TOKEN_SECRET", "token-secret")
    assert digest.verify_read_token(42, token) == 7


def test_session_secret_is_token_secret_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOKEN_SECRET", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "session-secret")
    token = digest._make_token(7, 42)

    monkeypatch.setenv("SESSION_SECRET", "different-session-secret")
    assert digest.verify_read_token(42, token) is None

    monkeypatch.setenv("SESSION_SECRET", "session-secret")
    assert digest.verify_read_token(42, token) == 7


def test_missing_token_secret_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOKEN_SECRET", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("TEST_SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="TOKEN_SECRET or SESSION_SECRET"):
        digest._make_token(7, 42)

    known_default_token = "7.68a42c06e2fd04b2cb418bddc1614281"  # noqa: S105
    assert digest.verify_read_token(42, known_default_token) is None


def test_token_is_rejected_for_wrong_article() -> None:
    token = digest._make_token(7, 42)
    assert digest.verify_read_token(43, token) is None


def test_token_rejects_garbage() -> None:
    assert digest.verify_read_token(42, "deadbeef") is None


def test_token_is_rejected_for_wrong_user_signature() -> None:
    token = digest._make_token(7, 42)
    replayed = token.replace("7.", "8.", 1)
    assert digest.verify_read_token(42, replayed) is None


# ── HTML / text rendering ─────────────────────────────────────────────────────


def test_render_html_includes_titles_and_mark_read_links() -> None:
    html = digest._render_html(_ARTICLES, user_id=7)
    assert "First Headline" in html
    # Missing title falls back to "Untitled".
    assert "Untitled" in html
    # Each article gets a signed mark-read link.
    assert f"/api/articles/1/read?token={digest._make_token(7, 1)}" in html


def test_render_html_pluralises_count() -> None:
    assert "1\n        new article today" in digest._render_html(_ARTICLES[:1], user_id=7)
    assert "article" in digest._render_html(_ARTICLES, user_id=7)


def test_render_text_lists_articles_in_order() -> None:
    text = digest._render_text(_ARTICLES, user_id=7)
    assert "1. First Headline" in text
    assert "2. Untitled" in text
    assert "Source: Example News | Score: 90" in text


# ── _send_email ───────────────────────────────────────────────────────────────


def test_send_email_skipped_when_not_configured() -> None:
    with (
        patch.dict("os.environ", {"SMTP_HOST": "", "DIGEST_TO": ""}, clear=False),
        patch("smtplib.SMTP") as smtp,
    ):
        digest._send_email("subj", "<p>html</p>", "text")
        smtp.assert_not_called()


def test_send_email_uses_starttls_on_standard_port() -> None:
    server = MagicMock()
    env = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "bot@example.com",
        "SMTP_PASS": "pw",
        "DIGEST_TO": "me@example.com",
    }
    with patch.dict("os.environ", env, clear=False), patch("smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = server
        digest._send_email("subj", "<p>html</p>", "text")

    server.starttls.assert_called_once()
    server.login.assert_called_once_with("bot@example.com", "pw")
    server.sendmail.assert_called_once()


def test_send_email_uses_ssl_on_port_465() -> None:
    server = MagicMock()
    env = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "465",
        "SMTP_USER": "bot@example.com",
        "SMTP_PASS": "pw",
        "DIGEST_TO": "me@example.com",
    }
    with patch.dict("os.environ", env, clear=False), patch("smtplib.SMTP_SSL") as smtp_ssl:
        smtp_ssl.return_value.__enter__.return_value = server
        digest._send_email("subj", "<p>html</p>", "text")

    smtp_ssl.assert_called_once()
    server.sendmail.assert_called_once()


# ── send_digest (integration) ─────────────────────────────────────────────────


@pytest.mark.postgres
def test_send_digest_returns_false_without_recipient(pg_clean: str) -> None:
    with patch.dict("os.environ", {"DIGEST_TO": ""}, clear=False):
        assert digest.send_digest() is False


@pytest.mark.postgres
def test_send_digest_returns_false_when_no_new_articles(pg_clean: str) -> None:
    with (
        patch.dict(
            "os.environ",
            {"DIGEST_TO": "me@example.com", "DIGEST_USER_ID": "1"},
            clear=False,
        ),
        patch.object(digest, "_send_email") as send,
    ):
        assert digest.send_digest() is False
        send.assert_not_called()


@pytest.mark.postgres
def test_send_digest_sends_when_new_articles_exist(pg_clean: str) -> None:
    user = create_user("digest-user", "pw", email="me@example.com", db_path=pg_clean)
    with psycopg.connect(pg_clean) as conn:
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind) VALUES (%s, %s, %s, %s, %s)",
            ("example-news", "Example News", "https://example.com/feed", "engineering", "rss"),
        )
        conn.execute(
            """
            INSERT INTO articles(
                url, canonical_url, title, source_slug, source_name,
                category, kind, status, importance_score, summary, reason, tags
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'new', %s, %s, %s, %s)
            """,
            (
                "https://example.com/a",
                "https://example.com/a",
                "Breaking",
                "example-news",
                "Example News",
                "engineering",
                "rss",
                88,
                "Summary.",
                "",
                "",
            ),
        )
        conn.commit()

    with (
        patch.dict(
            "os.environ",
            {"DIGEST_TO": "me@example.com", "DIGEST_USER_ID": str(user["id"])},
            clear=False,
        ),
        patch.object(digest, "_send_email") as send,
    ):
        assert digest.send_digest() is True
        send.assert_called_once()
        subject = send.call_args.args[0]
        assert "News Digest" in subject


@pytest.mark.postgres
def test_get_top_new_articles_uses_recipient_source_visibility(pg_clean: str) -> None:
    user = create_user("digest-user", "pw", email="me@example.com", db_path=pg_clean)
    with psycopg.connect(pg_clean) as conn:
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind) VALUES (%s, %s, %s, %s, %s)",
            ("visible", "Visible", "https://example.com/visible", "engineering", "rss"),
        )
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind) VALUES (%s, %s, %s, %s, %s)",
            ("hidden", "Hidden", "https://example.com/hidden", "engineering", "rss"),
        )
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (%s, %s, FALSE)",
            (user["id"], "hidden"),
        )
        for slug in ("visible", "hidden"):
            conn.execute(
                """
                INSERT INTO articles(
                    url, canonical_url, title, source_slug, source_name,
                    category, kind, state, importance_score
                ) VALUES (%s, %s, %s, %s, %s, 'engineering', 'rss', 'today', 90)
                """,
                (
                    f"https://example.com/{slug}/a",
                    f"https://example.com/{slug}/a",
                    slug,
                    slug,
                    slug.title(),
                ),
            )
        conn.commit()

    articles = digest._get_top_new_articles(int(user["id"]))
    assert {article["source_slug"] for article in articles} == {"visible"}


# ── HTML escaping ─────────────────────────────────────────────────────────────


def test_render_html_escapes_script_in_title() -> None:
    articles = [
        {
            "id": 1,
            "title": "<script>alert(1)</script>",
            "url": "https://example.com/1",
            "source_name": "Src",
            "summary": "ok",
            "importance_score": 50,
        }
    ]
    html = digest._render_html(articles, user_id=7)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_html_escapes_quotes_in_url() -> None:
    articles = [
        {
            "id": 2,
            "title": "Title",
            "url": 'https://example.com/?x="evil"',
            "source_name": "Src",
            "summary": "",
            "importance_score": 0,
        }
    ]
    html = digest._render_html(articles, user_id=7)
    assert '"evil"' not in html


def test_render_html_escapes_summary_and_source() -> None:
    articles = [
        {
            "id": 3,
            "title": "T",
            "url": "https://example.com/",
            "source_name": "<b>Bad Source</b>",
            "summary": "<em>bad summary</em>",
            "importance_score": 0,
        }
    ]
    html = digest._render_html(articles, user_id=7)
    assert "<b>" not in html
    assert "<em>" not in html
    assert "&lt;b&gt;" in html
    assert "&lt;em&gt;" in html


# ── Public token route (no session required) ──────────────────────────────────


def _fresh_client() -> TestClient:
    from news_dashboard.main import app

    app.dependency_overrides.clear()
    return TestClient(app, raise_server_exceptions=True)


@pytest.mark.postgres
def test_mark_read_via_token_succeeds_without_session(pg_clean: str) -> None:
    import psycopg

    user_a = create_user("alice", "pw", db_path=pg_clean)
    user_b = create_user("bob", "pw", db_path=pg_clean)
    with psycopg.connect(pg_clean) as conn:
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind) VALUES (%s, %s, %s, %s, %s)",
            ("src", "Src", "https://example.com/feed", "engineering", "rss"),
        )
        conn.execute(
            """
            INSERT INTO articles(
                url, canonical_url, title, source_slug, source_name,
                category, kind, status, state, importance_score, summary, reason, tags
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'new', 'today', 70, 'Sum', '', '')
            """,
            (
                "https://example.com/a",
                "https://example.com/a",
                "Headline",
                "src",
                "Src",
                "engineering",
                "rss",
            ),
        )
        row = conn.execute("SELECT id FROM articles LIMIT 1").fetchone()
        assert row is not None
        article_id: int = row[0]
        conn.commit()

    token = digest._make_token(int(user_a["id"]), article_id)
    client = _fresh_client()
    resp = client.get(f"/api/articles/{article_id}/read", params={"token": token}, cookies={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "marked_read"
    with psycopg.connect(pg_clean) as conn:
        states = conn.execute(
            "SELECT user_id, state FROM user_article_state WHERE article_id = %s ORDER BY user_id",
            (article_id,),
        ).fetchall()
        article_state = conn.execute(
            "SELECT status, state FROM articles WHERE id = %s",
            (article_id,),
        ).fetchone()
    assert [(row[0], row[1]) for row in states] == [(user_a["id"], "done")]
    assert article_state == ("new", "today")
    assert user_b["id"] not in {row[0] for row in states}


@pytest.mark.postgres
def test_mark_read_via_token_rejects_bad_token(pg_clean: str) -> None:
    client = _fresh_client()
    resp = client.get("/api/articles/999/read", params={"token": "badtoken"}, cookies={})
    assert resp.status_code == 403


@pytest.mark.postgres
def test_mark_read_via_token_rejects_wrong_article_token(pg_clean: str) -> None:
    token = digest._make_token(7, 1)
    client = _fresh_client()
    resp = client.get("/api/articles/2/read", params={"token": token}, cookies={})
    assert resp.status_code == 403
