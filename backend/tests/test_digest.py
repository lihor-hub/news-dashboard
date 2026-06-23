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

from news_dashboard import digest

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
    token = digest._make_token(42)
    assert digest.verify_read_token(42, token) is True


def test_token_is_rejected_for_wrong_article() -> None:
    token = digest._make_token(42)
    assert digest.verify_read_token(43, token) is False


def test_token_rejects_garbage() -> None:
    assert digest.verify_read_token(42, "deadbeef") is False


# ── HTML / text rendering ─────────────────────────────────────────────────────


def test_render_html_includes_titles_and_mark_read_links() -> None:
    html = digest._render_html(_ARTICLES)
    assert "First Headline" in html
    # Missing title falls back to "Untitled".
    assert "Untitled" in html
    # Each article gets a signed mark-read link.
    assert f"/api/articles/1/read?token={digest._make_token(1)}" in html


def test_render_html_pluralises_count() -> None:
    assert "1\n        new article today" in digest._render_html(_ARTICLES[:1])
    assert "article" in digest._render_html(_ARTICLES)


def test_render_text_lists_articles_in_order() -> None:
    text = digest._render_text(_ARTICLES)
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
        patch.dict("os.environ", {"DIGEST_TO": "me@example.com"}, clear=False),
        patch.object(digest, "_send_email") as send,
    ):
        assert digest.send_digest() is False
        send.assert_not_called()


@pytest.mark.postgres
def test_send_digest_sends_when_new_articles_exist(pg_clean: str) -> None:
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
        patch.dict("os.environ", {"DIGEST_TO": "me@example.com"}, clear=False),
        patch.object(digest, "_send_email") as send,
    ):
        assert digest.send_digest() is True
        send.assert_called_once()
        subject = send.call_args.args[0]
        assert "News Digest" in subject
