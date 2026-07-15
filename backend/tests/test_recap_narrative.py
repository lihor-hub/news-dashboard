"""Tests for the AI weekly recap narrative generator."""

from __future__ import annotations

from typing import Any
from unittest.mock import ANY, MagicMock, patch

import pytest

from news_dashboard.ai_client import ManagedPrompt
from news_dashboard.recaps.narrative import generate_recap_narrative


def _make_recap(**overrides: object) -> dict[str, object]:
    recap: dict[str, object] = {
        "week_start": "2026-06-22",
        "week_end": "2026-06-29",
        "generated_at": "2026-06-29T09:00:00+00:00",
        "articles_read": 12,
        "categories": [{"category": "science", "count": 5}],
        "sources": [{"source": "Example News", "count": 4}],
        "minutes_read": 45.0,
        "current_streak_days": 3,
    }
    recap.update(overrides)
    return recap


def test_generate_recap_narrative_falls_back_when_no_api_key() -> None:
    with patch("news_dashboard.ai_client.free_llm_config", return_value=("", None)):
        result = generate_recap_narrative(_make_recap())

    assert "12" in result


def test_generate_recap_narrative_falls_back_with_zero_articles() -> None:
    with patch("news_dashboard.ai_client.free_llm_config", return_value=("", None)):
        result = generate_recap_narrative(_make_recap(articles_read=0, categories=[]))

    assert result
    assert "0" not in result or "didn't read" in result


def test_generate_recap_narrative_returns_llm_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    narrative_text = (
        "You had a strong week, reading 12 articles mostly about science.\n\n"
        "Keep up the streak — three days running is great momentum."
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=narrative_text))]
    )
    completion = mock_client.chat.completions.create.return_value
    managed_prompt = ManagedPrompt(text="compiled recap narrative")

    with (
        patch("news_dashboard.ai_client.get_chat_client", return_value=mock_client),
        patch("news_dashboard.ai_client.chat_create", return_value=completion) as chat_create,
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
        patch("news_dashboard.ai_client.get_prompt", return_value=managed_prompt) as get_prompt,
    ):
        result = generate_recap_narrative(_make_recap())

    assert result == narrative_text
    call_kwargs = chat_create.call_args.kwargs
    recap_json = get_prompt.call_args.kwargs["variables"]["recap_json"]
    assert "12" in recap_json
    get_prompt.assert_called_once_with(
        "weekly-recap-narrative",
        fallback=ANY,
        label="production",
        prompt_type="text",
        variables={"recap_json": recap_json},
    )
    assert call_kwargs["prompt"] is managed_prompt


def test_generate_recap_narrative_falls_back_on_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("LLM unavailable")

    with (
        patch("news_dashboard.ai_client.get_chat_client", return_value=mock_client),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        result = generate_recap_narrative(_make_recap())

    assert "12" in result
    mock_client.chat.completions.create.assert_called_once()


def test_generate_recap_narrative_mentions_saved_and_dwell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    captured_prompt: list[str] = []

    def fake_create(**kwargs: Any) -> MagicMock:
        captured_prompt.append(kwargs["messages"][0]["content"])
        return MagicMock(choices=[MagicMock(message=MagicMock(content="Narrative."))])

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = fake_create

    recap = _make_recap(
        saved={"starred_this_week": 2, "read_from_backlog": 1, "backlog_total": 8},
        dwell={"skims": 3, "reads": 9, "average_seconds": 42.0},
    )

    with (
        patch("news_dashboard.ai_client.get_chat_client", return_value=mock_client),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        generate_recap_narrative(recap)

    prompt = captured_prompt[0]
    assert "backlog_total" in prompt
    assert "average_seconds" in prompt
    assert "generated_at" not in prompt
