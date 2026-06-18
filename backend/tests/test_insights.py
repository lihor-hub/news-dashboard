"""Unit tests for news_dashboard.insights.

All OpenAI calls are mocked — no network or live API key needed.
DB-touching tests use the pg_clean fixture (live Postgres).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from news_dashboard.db import connect
from news_dashboard.insights import (
    InsightsNotConfiguredError,
    _build_text,
    _parse_bullets,
    generate_insights,
    get_or_generate_insights,
)

# ── shared test data ──────────────────────────────────────────────────────────

_ARTICLE: dict[str, Any] = {
    "id": 1,
    "title": "Test Headline",
    "body": "This is the body text.",
    "summary": "Short summary.",
}

_ARTICLE_NO_BODY: dict[str, Any] = {
    "id": 2,
    "title": "No Body",
    "body": None,
    "summary": "Only a summary.",
}

_ARTICLE_EMPTY: dict[str, Any] = {
    "id": 3,
    "title": "",
    "body": None,
    "summary": "",
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _seed_article(pg_url: str, *, insights: str | None = None) -> int:
    """Insert a minimal article row and return its id."""
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind)
            VALUES ('test-src', 'Test', 'https://example.com', 'tech', 'rss_feed')
            ON CONFLICT(slug) DO NOTHING
            """
        )
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, summary, insights
            )
            VALUES (
              'https://example.com/a', 'https://example.com/a',
              'Test Headline', 'test-src', 'Test', 'tech', 'rss_feed',
              'A short summary.', %s
            )
            RETURNING id
            """,
            (insights,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


# ── _parse_bullets ────────────────────────────────────────────────────────────


def test_parse_bullets_standard_format() -> None:
    text = "• First insight\n• Second insight\n• Third insight"
    assert _parse_bullets(text) == ["First insight", "Second insight", "Third insight"]


def test_parse_bullets_strips_whitespace() -> None:
    text = "  •  Padded bullet  \n• Another"
    assert _parse_bullets(text) == ["Padded bullet", "Another"]


def test_parse_bullets_ignores_non_bullet_lines() -> None:
    text = "Here are the bullets:\n• Real bullet\nSome prose line\n• Another bullet"
    assert _parse_bullets(text) == ["Real bullet", "Another bullet"]


def test_parse_bullets_empty_string() -> None:
    assert _parse_bullets("") == []


def test_parse_bullets_no_bullets() -> None:
    assert _parse_bullets("No bullets here at all.") == []


# ── _build_text ───────────────────────────────────────────────────────────────


def test_build_text_uses_body_when_longer_than_summary() -> None:
    text = _build_text(_ARTICLE)
    assert "body text" in text
    assert "Short summary" not in text


def test_build_text_falls_back_to_summary_when_no_body() -> None:
    text = _build_text(_ARTICLE_NO_BODY)
    assert "Only a summary" in text


def test_build_text_includes_title() -> None:
    text = _build_text(_ARTICLE)
    assert "Test Headline" in text


# ── generate_insights ─────────────────────────────────────────────────────────


def test_generate_insights_raises_without_api_key() -> None:
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("OPENAI_API_KEY", None)
        with pytest.raises(InsightsNotConfiguredError):
            generate_insights(_ARTICLE)


def test_generate_insights_returns_parsed_bullets() -> None:
    mock_completion = MagicMock()
    mock_completion.choices[
        0
    ].message.content = "• First bullet point\n• Second bullet point\n• Third bullet point"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        bullets = generate_insights(_ARTICLE)

    assert bullets == ["First bullet point", "Second bullet point", "Third bullet point"]
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert "Test Headline" in call_kwargs["messages"][0]["content"]


def test_generate_insights_returns_empty_list_for_empty_article() -> None:
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
        result = generate_insights(_ARTICLE_EMPTY)
    assert result == []


# ── get_or_generate_insights ──────────────────────────────────────────────────


def test_get_or_generate_insights_returns_cached_without_api_call(pg_clean: str) -> None:
    cached = ["Cached bullet 1", "Cached bullet 2"]
    article_id = _seed_article(pg_clean, insights=json.dumps(cached))

    mock_client = MagicMock()
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        result = get_or_generate_insights(article_id, database_url=pg_clean)

    assert result == cached
    mock_client.chat.completions.create.assert_not_called()


def test_get_or_generate_insights_generates_and_caches_when_missing(pg_clean: str) -> None:
    article_id = _seed_article(pg_clean)

    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "• New bullet\n• Another bullet"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    fake_article = {
        "id": article_id,
        "title": "Test Headline",
        "body": "body text",
        "summary": "A short summary.",
    }

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
        patch("news_dashboard.insights.get_article", return_value=fake_article),
    ):
        result = get_or_generate_insights(article_id, database_url=pg_clean)

    assert result == ["New bullet", "Another bullet"]
    mock_client.chat.completions.create.assert_called_once()

    with connect(database_url=pg_clean) as conn:
        row = conn.execute("SELECT insights FROM articles WHERE id = %s", (article_id,)).fetchone()
    stored = row["insights"] if isinstance(row, dict) else row[0]
    assert json.loads(stored) == ["New bullet", "Another bullet"]


def test_get_or_generate_insights_raises_without_api_key_when_not_cached(pg_clean: str) -> None:
    article_id = _seed_article(pg_clean)

    fake_article = {"id": article_id, "title": "T", "body": "body", "summary": "s"}

    with (
        patch.dict("os.environ", {}, clear=False),
        patch("news_dashboard.insights.get_article", return_value=fake_article),
    ):
        import os

        os.environ.pop("OPENAI_API_KEY", None)
        with pytest.raises(InsightsNotConfiguredError):
            get_or_generate_insights(article_id, database_url=pg_clean)


def test_get_or_generate_insights_second_call_uses_cache(pg_clean: str) -> None:
    article_id = _seed_article(pg_clean)
    call_count: list[int] = []

    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "• Bullet"
    mock_client = MagicMock()

    def count_call(**_kwargs: object) -> object:
        call_count.append(1)
        return mock_completion

    mock_client.chat.completions.create.side_effect = count_call

    fake_article = {"id": article_id, "title": "T", "body": "body", "summary": "s"}

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
        patch("news_dashboard.insights.get_article", return_value=fake_article),
    ):
        r1 = get_or_generate_insights(article_id, database_url=pg_clean)
        r2 = get_or_generate_insights(article_id, database_url=pg_clean)

    assert r1 == r2 == ["Bullet"]
    assert len(call_count) == 1, "AI called more than once — cache not working"


def test_get_or_generate_insights_returns_empty_for_missing_article(pg_clean: str) -> None:
    result = get_or_generate_insights(99999, database_url=pg_clean)
    assert result == []
