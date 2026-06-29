"""Unit tests for news_dashboard.perspectives.

All OpenAI calls are mocked — no network or live API key needed.
DB-touching tests use the pg_clean fixture (live Postgres).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from news_dashboard.db import connect
from news_dashboard.perspectives import (
    DEFAULT_PERSPECTIVES_MODEL,
    PerspectivesNotConfiguredError,
    _build_text,
    _fetch_related_articles,
    _parse_analysis,
    _perspectives_ai_config,
    generate_perspectives,
    get_or_generate_perspectives,
)

# ── shared test data ──────────────────────────────────────────────────────────

_ARTICLE: dict[str, Any] = {
    "id": 1,
    "title": "Test Headline",
    "body": "This is the body text about a major event.",
    "summary": "Short summary.",
}

_ARTICLE_EMPTY: dict[str, Any] = {
    "id": 3,
    "title": "",
    "body": None,
    "summary": "",
}

_VALID_ANALYSIS = {
    "verified_facts": ["Fact one"],
    "omissions": ["Missing context"],
    "alternative_perspectives": ["Counter view"],
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _seed_article(pg_url: str, *, perspective_analysis: str | None = None) -> int:
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
              category, kind, summary, perspective_analysis
            )
            VALUES (
              'https://example.com/p', 'https://example.com/p',
              'Test Headline', 'test-src', 'Test', 'tech', 'rss_feed',
              'A short summary.', %s
            )
            RETURNING id
            """,
            (perspective_analysis,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _seed_user(pg_url: str, username: str) -> int:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'x') RETURNING id",
            (username,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _seed_private_article(
    pg_url: str,
    *,
    owner_user_id: int,
    url_slug: str = "priv-p",
    category: str = "tech",
    perspective_analysis: str | None = None,
) -> int:
    slug = f"private-src-{url_slug}"
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, owner_user_id)
            VALUES (%s, 'Private', %s, %s, 'rss_feed', %s)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, f"https://{slug}.example", category, owner_user_id),
        )
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, summary, body, perspective_analysis
            )
            VALUES (
              %s, %s, 'Private Article', %s, 'Private', %s,
              'rss_feed', 'Summary.', 'Body text here.', %s
            )
            RETURNING id
            """,
            (
                f"https://{slug}.example/a",
                f"https://{slug}.example/a",
                slug,
                category,
                perspective_analysis,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


# ── _parse_analysis ───────────────────────────────────────────────────────────


def test_parse_analysis_valid_json() -> None:
    text = json.dumps(_VALID_ANALYSIS)
    result = _parse_analysis(text)
    assert result["verified_facts"] == ["Fact one"]
    assert result["omissions"] == ["Missing context"]
    assert result["alternative_perspectives"] == ["Counter view"]


def test_parse_analysis_strips_markdown_fences() -> None:
    text = f"```json\n{json.dumps(_VALID_ANALYSIS)}\n```"
    result = _parse_analysis(text)
    assert result["verified_facts"] == ["Fact one"]


def test_parse_analysis_returns_empty_on_invalid_json() -> None:
    result = _parse_analysis("not json at all")
    assert result == {
        "verified_facts": [],
        "omissions": [],
        "alternative_perspectives": [],
    }


def test_parse_analysis_filters_blank_items() -> None:
    data = {"verified_facts": ["  ", "Real fact"], "omissions": [], "alternative_perspectives": []}
    result = _parse_analysis(json.dumps(data))
    assert result["verified_facts"] == ["Real fact"]


# ── _build_text ───────────────────────────────────────────────────────────────


def test_build_text_includes_title_and_body() -> None:
    text = _build_text(_ARTICLE, [])
    assert "Test Headline" in text
    assert "body text" in text


def test_build_text_appends_related_articles() -> None:
    related = [{"title": "Related", "body": "Related body", "summary": ""}]
    text = _build_text(_ARTICLE, related)
    assert "Related articles" in text
    assert "Related" in text


def test_build_text_empty_article_returns_empty() -> None:
    text = _build_text(_ARTICLE_EMPTY, [])
    assert text.strip() == ""


# ── _perspectives_ai_config ───────────────────────────────────────────────────


def test_perspectives_ai_config_raises_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    with pytest.raises(PerspectivesNotConfiguredError):
        _perspectives_ai_config()


def test_perspectives_ai_config_uses_free_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "sk-free-llm")
    monkeypatch.setenv("FREE_LLM_BASE_URL", "http://gateway/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    api_key, base_url, model = _perspectives_ai_config()
    assert api_key == "sk-free-llm"
    assert base_url == "http://gateway/v1"
    assert model == DEFAULT_PERSPECTIVES_MODEL


def test_perspectives_ai_config_falls_back_to_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-shared")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://gateway/v1")
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("FREE_LLM_BASE_URL", raising=False)
    api_key, base_url, model = _perspectives_ai_config()
    assert api_key == "sk-shared"
    assert base_url == "http://gateway/v1"
    assert model == DEFAULT_PERSPECTIVES_MODEL


def test_perspectives_ai_config_uses_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-shared")
    monkeypatch.setenv("OPENAI_PERSPECTIVES_MODEL", "custom-model")
    _, _, model = _perspectives_ai_config()
    assert model == "custom-model"


# ── generate_perspectives ─────────────────────────────────────────────────────


def test_generate_perspectives_returns_parsed_analysis() -> None:
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = json.dumps(_VALID_ANALYSIS)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        result = generate_perspectives(_ARTICLE)

    assert result["verified_facts"] == ["Fact one"]
    assert result["omissions"] == ["Missing context"]
    assert result["alternative_perspectives"] == ["Counter view"]
    mock_client.chat.completions.create.assert_called_once()


def test_generate_perspectives_returns_empty_for_empty_article() -> None:
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
        result = generate_perspectives(_ARTICLE_EMPTY)
    assert result == {"verified_facts": [], "omissions": [], "alternative_perspectives": []}


def test_generate_perspectives_raises_without_api_key() -> None:
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("FREE_LLM_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        with pytest.raises(PerspectivesNotConfiguredError):
            generate_perspectives(_ARTICLE)


# ── get_or_generate_perspectives ─────────────────────────────────────────────


def test_get_or_generate_returns_cached_without_api_call(pg_clean: str) -> None:
    cached = json.dumps(_VALID_ANALYSIS)
    article_id = _seed_article(pg_clean, perspective_analysis=cached)

    mock_client = MagicMock()
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        result = get_or_generate_perspectives(article_id, database_url=pg_clean)

    assert result is not None
    assert result["verified_facts"] == ["Fact one"]
    mock_client.chat.completions.create.assert_not_called()


def test_get_or_generate_generates_and_caches_when_missing(pg_clean: str) -> None:
    article_id = _seed_article(pg_clean)

    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = json.dumps(_VALID_ANALYSIS)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    fake_article = {
        "id": article_id,
        "title": "Test Headline",
        "body": "body text about a major event",
        "summary": "A short summary.",
    }

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
        patch("news_dashboard.perspectives.get_article", return_value=fake_article),
    ):
        result = get_or_generate_perspectives(article_id, database_url=pg_clean)

    assert result is not None
    assert result["verified_facts"] == ["Fact one"]
    mock_client.chat.completions.create.assert_called_once()

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT perspective_analysis FROM articles WHERE id = %s", (article_id,)
        ).fetchone()
    stored = row["perspective_analysis"] if isinstance(row, dict) else row[0]
    parsed = json.loads(stored) if isinstance(stored, str) else stored
    assert parsed["verified_facts"] == ["Fact one"]


def test_get_or_generate_returns_none_for_missing_article(pg_clean: str) -> None:
    result = get_or_generate_perspectives(99999, database_url=pg_clean)
    assert result is None


def test_get_or_generate_returns_empty_when_no_body(pg_clean: str) -> None:
    article_id = _seed_article(pg_clean)

    mock_client = MagicMock()
    fake_article = {"id": article_id, "title": "T", "body": None, "summary": "s"}

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
        patch("news_dashboard.perspectives.get_article", return_value=fake_article),
    ):
        result = get_or_generate_perspectives(article_id, database_url=pg_clean)

    assert result == {"verified_facts": [], "omissions": [], "alternative_perspectives": []}
    mock_client.chat.completions.create.assert_not_called()


def test_get_or_generate_second_call_uses_cache(pg_clean: str) -> None:
    article_id = _seed_article(pg_clean)
    call_count: list[int] = []

    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = json.dumps(_VALID_ANALYSIS)
    mock_client = MagicMock()

    def count_call(**_kwargs: object) -> object:
        call_count.append(1)
        return mock_completion

    mock_client.chat.completions.create.side_effect = count_call
    fake_article = {"id": article_id, "title": "T", "body": "body text", "summary": "s"}

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
        patch("news_dashboard.perspectives.get_article", return_value=fake_article),
    ):
        r1 = get_or_generate_perspectives(article_id, database_url=pg_clean)
        r2 = get_or_generate_perspectives(article_id, database_url=pg_clean)

    assert r1 == r2
    assert len(call_count) == 1, "AI called more than once — cache not working"


# ── visibility / authorization tests ─────────────────────────────────────────


def test_get_or_generate_returns_none_for_unauthorized_user_cached(pg_clean: str) -> None:
    """Cached perspectives for a private article must not be returned to another user."""
    owner_id = _seed_user(pg_clean, "owner-p-1")
    other_id = _seed_user(pg_clean, "other-p-1")
    article_id = _seed_private_article(
        pg_clean,
        owner_user_id=owner_id,
        url_slug="vis1",
        perspective_analysis=json.dumps(_VALID_ANALYSIS),
    )

    result = get_or_generate_perspectives(article_id, user_id=other_id, database_url=pg_clean)

    assert result is None


def test_get_or_generate_returns_cached_for_owner(pg_clean: str) -> None:
    """Owner can still retrieve cached perspectives for their private article."""
    owner_id = _seed_user(pg_clean, "owner-p-2")
    article_id = _seed_private_article(
        pg_clean,
        owner_user_id=owner_id,
        url_slug="vis2",
        perspective_analysis=json.dumps(_VALID_ANALYSIS),
    )

    result = get_or_generate_perspectives(article_id, user_id=owner_id, database_url=pg_clean)

    assert result is not None
    assert result["verified_facts"] == ["Fact one"]


def test_fetch_related_articles_excludes_invisible_sources(pg_clean: str) -> None:
    """Related articles from sources invisible to the user must be excluded."""
    owner_id = _seed_user(pg_clean, "owner-p-3")
    other_id = _seed_user(pg_clean, "other-p-3")

    pivot_id = _seed_private_article(
        pg_clean, owner_user_id=owner_id, url_slug="pivot", category="tech"
    )
    _seed_private_article(pg_clean, owner_user_id=owner_id, url_slug="related1", category="tech")

    related_as_owner = _fetch_related_articles(pivot_id, user_id=owner_id, database_url=pg_clean)
    related_as_other = _fetch_related_articles(pivot_id, user_id=other_id, database_url=pg_clean)

    assert len(related_as_owner) == 1
    assert len(related_as_other) == 0


def test_perspectives_endpoint_returns_404_for_unauthorized_cached(pg_clean: str) -> None:
    """GET /api/articles/{id}/perspectives returns 404 when user cannot access the article."""
    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    owner_id = _seed_user(pg_clean, "owner-p-4")
    other_id = _seed_user(pg_clean, "other-p-4")
    article_id = _seed_private_article(
        pg_clean,
        owner_user_id=owner_id,
        url_slug="vis4",
        perspective_analysis=json.dumps(_VALID_ANALYSIS),
    )

    other_user = {"id": other_id, "is_admin": False, "username": "other-p-4"}
    app.dependency_overrides[require_auth] = lambda: other_user
    try:
        client = TestClient(app)
        resp = client.get(f"/api/articles/{article_id}/perspectives")
    finally:
        del app.dependency_overrides[require_auth]

    assert resp.status_code == 404
