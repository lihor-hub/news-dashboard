"""Unit tests for news_dashboard.insights.

All OpenAI calls are mocked — no network or live API key needed.
DB-touching tests use the pg_clean fixture (live Postgres).
"""

from __future__ import annotations

import json
import struct
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from news_dashboard.db import connect
from news_dashboard.insights import (
    DEFAULT_INSIGHTS_MODEL,
    InsightsNotConfiguredError,
    _build_text,
    _cosine_sim,
    _greedy_cluster,
    _insights_ai_config,
    _normalize,
    _parse_bullets,
    _pca_2d,
    _vec_mean,
    cluster_recent_articles,
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

        os.environ.pop("OPENAI_INSIGHTS_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        with pytest.raises(InsightsNotConfiguredError):
            generate_insights(_ARTICLE)


def test_insights_ai_config_uses_gateway_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://shared-gateway:9130/v1")

    api_key, base_url, model = _insights_ai_config()

    assert api_key == "sk-openai"
    assert base_url == "http://shared-gateway:9130/v1"
    assert model == DEFAULT_INSIGHTS_MODEL


def test_insights_ai_config_prefers_insights_gateway_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://shared-gateway/v1")
    monkeypatch.setenv("OPENAI_INSIGHTS_API_KEY", "freellmapi-key")
    monkeypatch.setenv("OPENAI_INSIGHTS_BASE_URL", "http://insights-gateway/v1")
    monkeypatch.setenv("OPENAI_INSIGHTS_MODEL", "gateway-chat-model")

    api_key, base_url, model = _insights_ai_config()

    assert api_key == "freellmapi-key"
    assert base_url == "http://insights-gateway/v1"
    assert model == "gateway-chat-model"


def test_insights_ai_config_falls_back_to_openai_when_gateway_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_INSIGHTS_BASE_URL", raising=False)

    api_key, base_url, model = _insights_ai_config()

    assert api_key == "sk-openai"
    assert base_url is None
    assert model == DEFAULT_INSIGHTS_MODEL


def test_generate_insights_returns_parsed_bullets() -> None:
    mock_completion = MagicMock()
    mock_completion.choices[
        0
    ].message.content = "• First bullet point\n• Second bullet point\n• Third bullet point"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with (
        patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_BASE_URL": "http://shared-gateway:9130/v1",
                "OPENAI_INSIGHTS_MODEL": "gateway-chat-model",
            },
        ),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        bullets = generate_insights(_ARTICLE)

    assert bullets == ["First bullet point", "Second bullet point", "Third bullet point"]
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gateway-chat-model"
    assert "Test Headline" in call_kwargs["messages"][0]["content"]


def test_generate_insights_returns_empty_list_for_empty_article() -> None:
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
        result = generate_insights(_ARTICLE_EMPTY)
    assert result == []


def test_generate_insights_prompt_grounds_in_article_text() -> None:
    """Prompt must explicitly forbid speculation beyond article content."""
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "• A bullet"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        generate_insights(_ARTICLE)

    prompt_text: str = mock_client.chat.completions.create.call_args.kwargs["messages"][0][
        "content"
    ]
    assert "ONLY" in prompt_text
    assert "speculation" in prompt_text
    assert "fewer bullets" in prompt_text


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


def test_get_or_generate_insights_returns_empty_when_body_not_fetched(pg_clean: str) -> None:
    """Must not call AI when body is absent — prevents hallucination from headline alone."""
    article_id = _seed_article(pg_clean)

    mock_client = MagicMock()
    fake_article_no_body = {
        "id": article_id,
        "title": "Test Headline",
        "body": None,
        "summary": "A short summary.",
    }

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
        patch("news_dashboard.insights.get_article", return_value=fake_article_no_body),
    ):
        result = get_or_generate_insights(article_id, database_url=pg_clean)

    assert result == []
    mock_client.chat.completions.create.assert_not_called()


def test_get_or_generate_insights_returns_empty_when_body_is_empty_string(pg_clean: str) -> None:
    article_id = _seed_article(pg_clean)

    mock_client = MagicMock()
    fake_article_empty_body = {
        "id": article_id,
        "title": "Test Headline",
        "body": "   ",
        "summary": "A short summary.",
    }

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
        patch("news_dashboard.insights.get_article", return_value=fake_article_empty_body),
    ):
        result = get_or_generate_insights(article_id, database_url=pg_clean)

    assert result == []
    mock_client.chat.completions.create.assert_not_called()


# ── clustering unit tests (no DB, no AI) ─────────────────────────────────────


def _pack_vec(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unit_vec(dim: int, idx: int) -> list[float]:
    """Return a unit vector with 1.0 at position idx."""
    v = [0.0] * dim
    v[idx] = 1.0
    return v


def test_normalize_zero_vector() -> None:
    result = _normalize([0.0, 0.0, 0.0])
    assert result == [0.0, 0.0, 0.0]


def test_normalize_unit_vector() -> None:
    result = _normalize([3.0, 4.0])
    assert abs(result[0] - 0.6) < 1e-6
    assert abs(result[1] - 0.8) < 1e-6


def test_cosine_sim_identical() -> None:
    v = [1.0, 0.0, 0.5]
    assert abs(_cosine_sim(v, v) - 1.0) < 1e-6


def test_cosine_sim_orthogonal() -> None:
    assert abs(_cosine_sim([1.0, 0.0], [0.0, 1.0])) < 1e-6


def test_vec_mean_basic() -> None:
    vecs = [[1.0, 2.0], [3.0, 4.0]]
    result = _vec_mean(vecs)
    assert result == [2.0, 3.0]


def test_greedy_cluster_groups_similar() -> None:
    a = _normalize([1.0, 0.0, 0.0])
    b = _normalize([0.99, 0.1, 0.0])
    c = _normalize([0.98, 0.12, 0.0])
    x = _normalize([0.0, 0.0, 1.0])
    y = _normalize([0.0, 0.05, 0.99])
    z = _normalize([0.0, 0.02, 0.999])

    assignments = _greedy_cluster([a, b, c, x, y, z], threshold=0.9)
    group1 = {assignments[0], assignments[1], assignments[2]}
    group2 = {assignments[3], assignments[4], assignments[5]}
    assert len(group1) == 1, "a, b, c should be in the same cluster"
    assert len(group2) == 1, "x, y, z should be in the same cluster"
    assert group1 != group2, "the two groups should be in different clusters"


def test_greedy_cluster_all_distinct() -> None:
    vecs = [_unit_vec(4, i) for i in range(4)]
    assignments = _greedy_cluster(vecs, threshold=0.9)
    assert len(set(assignments)) == 4


def test_pca_2d_single_vector() -> None:
    coords = _pca_2d([[1.0, 0.0, 0.5]])
    assert coords == [(0.0, 0.0)]


def test_pca_2d_two_vectors() -> None:
    coords = _pca_2d([[1.0, 0.0], [0.0, 1.0]])
    assert len(coords) == 2
    assert coords[0][0] != coords[1][0] or coords[0][1] != coords[1][1]


def test_pca_2d_multiple_vectors_normalized() -> None:
    vecs = [[float(i), float(j)] for i in range(4) for j in range(4)]
    coords = _pca_2d(vecs)
    assert len(coords) == len(vecs)
    for x, y in coords:
        assert -1.01 <= x <= 1.01
        assert -1.01 <= y <= 1.01


def test_cluster_recent_articles_returns_empty_when_no_articles(pg_clean: str) -> None:
    result = cluster_recent_articles(database_url=pg_clean)
    assert result == []


def _seed_articles_with_embeddings(pg_url: str, groups: list[list[list[float]]]) -> list[int]:
    """Seed articles with embeddings in groups. Returns article IDs."""
    ids: list[int] = []
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind)
            VALUES ('test-src2', 'Test2', 'https://example2.com', 'tech', 'rss_feed')
            ON CONFLICT(slug) DO NOTHING
            """
        )
        for group_idx, group in enumerate(groups):
            for vec_idx, vec in enumerate(group):
                blob = _pack_vec(vec)
                row = conn.execute(
                    """
                    INSERT INTO articles(
                      url, canonical_url, title, source_slug, source_name,
                      category, kind, summary, embedding,
                      discovered_at
                    )
                    VALUES (
                      %s, %s, %s, 'test-src2', 'Test2', 'tech', 'rss_feed',
                      %s, %s,
                      NOW()
                    )
                    RETURNING id
                    """,
                    (
                        f"https://example2.com/g{group_idx}-v{vec_idx}",
                        f"https://example2.com/g{group_idx}-v{vec_idx}",
                        f"Article G{group_idx} V{vec_idx}",
                        f"Summary for group {group_idx} article {vec_idx}",
                        blob,
                    ),
                ).fetchone()
                assert row is not None
                ids.append(int(row["id"]))
    return ids


def test_cluster_recent_articles_groups_similar_embeddings(pg_clean: str) -> None:
    """Articles with near-identical embeddings should form clusters."""
    dim = 16
    group_a = [
        _normalize([1.0 if j == 0 else 0.01 * j for j in range(dim)]),
        _normalize([1.0 if j == 0 else 0.011 * j for j in range(dim)]),
        _normalize([1.0 if j == 0 else 0.012 * j for j in range(dim)]),
    ]
    group_b = [
        _normalize([0.0 if j != dim - 1 else 1.0 for j in range(dim)]),
        _normalize([0.0 if j != dim - 1 else 1.0 if j == dim - 1 else 0.01 for j in range(dim)]),
        _normalize([0.01 if j != dim - 1 else 1.0 for j in range(dim)]),
    ]

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "HEADLINE: Test\nSUMMARY: A test cluster."
    mock_client.chat.completions.create.return_value = mock_response

    _seed_articles_with_embeddings(pg_clean, [group_a, group_b])

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        clusters = cluster_recent_articles(database_url=pg_clean)

    assert len(clusters) >= 1
    for cluster in clusters:
        assert "headline" in cluster
        assert "trend_summary" in cluster
        assert "x" in cluster
        assert "y" in cluster
        assert "article_ids" in cluster
        assert len(cluster["articles"]) >= 3


def test_cluster_recent_articles_returns_empty_below_min_size(pg_clean: str) -> None:
    """Only 2 similar articles — below min size of 3 — should yield no clusters."""
    dim = 8
    group = [
        _normalize([1.0 if j == 0 else 0.01 for j in range(dim)]),
        _normalize([1.0 if j == 0 else 0.012 for j in range(dim)]),
    ]

    _seed_articles_with_embeddings(pg_clean, [group])

    result = cluster_recent_articles(database_url=pg_clean)
    assert result == []
