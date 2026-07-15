"""Tests for the AI weekly learning recap narrative generator."""

from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

import pytest

from news_dashboard.ai_client import ManagedPrompt
from news_dashboard.lesson_recaps.narrative import generate_lesson_recap_narrative


def _make_recap(**overrides: object) -> dict[str, object]:
    recap: dict[str, object] = {
        "week_start": "2026-06-22",
        "week_end": "2026-06-29",
        "generated_at": "2026-06-29T09:00:00+00:00",
        "lessons_touched": 4,
        "lessons_completed": 3,
        "key_concepts": [{"concept": "gradient descent", "count": 2}],
        "repeated_themes": [{"concept": "gradient descent", "count": 2}],
        "unfinished_lessons": [],
        "notable_articles": [{"id": 1, "title": "Backprop Explained", "source_name": "Example"}],
    }
    recap.update(overrides)
    return recap


def test_generate_lesson_recap_narrative_falls_back_when_no_api_key() -> None:
    with patch("news_dashboard.ai_client.free_llm_config", return_value=("", None)):
        result = generate_lesson_recap_narrative(_make_recap())

    assert "3" in result


def test_generate_lesson_recap_narrative_falls_back_with_zero_lessons() -> None:
    with patch("news_dashboard.ai_client.free_llm_config", return_value=("", None)):
        result = generate_lesson_recap_narrative(_make_recap(lessons_completed=0, key_concepts=[]))

    assert result
    assert "didn't finish" in result


def test_generate_lesson_recap_narrative_returns_llm_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    narrative_text = (
        "You completed 3 lessons this week, circling back to gradient descent.\n\n"
        "Consider finishing your remaining lesson to close out the trail."
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=narrative_text))]
    )
    completion = mock_client.chat.completions.create.return_value
    managed_prompt = ManagedPrompt(text="compiled lesson recap narrative")

    with (
        patch("news_dashboard.ai_client.get_chat_client", return_value=mock_client),
        patch("news_dashboard.ai_client.chat_create", return_value=completion) as chat_create,
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
        patch("news_dashboard.ai_client.get_prompt", return_value=managed_prompt) as get_prompt,
    ):
        result = generate_lesson_recap_narrative(_make_recap())

    assert result == narrative_text
    recap_json = get_prompt.call_args.kwargs["variables"]["recap_json"]
    assert "gradient descent" in recap_json
    get_prompt.assert_called_once_with(
        "weekly-lesson-recap-narrative",
        fallback=ANY,
        label="production",
        prompt_type="text",
        variables={"recap_json": recap_json},
    )
    assert chat_create.call_args.kwargs["prompt"] is managed_prompt


def test_generate_lesson_recap_narrative_falls_back_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("LLM unavailable")

    with (
        patch("news_dashboard.ai_client.get_chat_client", return_value=mock_client),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        result = generate_lesson_recap_narrative(_make_recap())

    assert "3" in result
    mock_client.chat.completions.create.assert_called_once()
