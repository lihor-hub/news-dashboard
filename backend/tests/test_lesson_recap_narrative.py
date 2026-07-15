"""Tests for the AI weekly learning recap narrative generator."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

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
    from langchain_core.callbacks import BaseCallbackHandler

    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("OPENAI_BRIEFING_MODEL", "gpt-4o-mini")

    narrative_text = (
        "You completed 3 lessons this week, circling back to gradient descent.\n\n"
        "Consider finishing your remaining lesson to close out the trail."
    )
    captured: dict[str, Any] = {}
    callback = BaseCallbackHandler()

    def fake_invoke(messages: Any, config: Any, **_kwargs: Any) -> AIMessage:
        captured.update(messages=messages, config=config)
        return AIMessage(content=narrative_text)

    with (
        patch(
            "news_dashboard.ai_client.get_chat_model",
            return_value=RunnableLambda(fake_invoke),
        ) as factory,
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
        patch("news_dashboard.ai_client.langfuse_enabled", return_value=True),
        patch("langfuse.langchain.CallbackHandler", return_value=callback),
        patch("langfuse.propagate_attributes") as attributes,
    ):
        result = generate_lesson_recap_narrative(_make_recap())

    assert result == narrative_text
    factory.assert_called_once_with(
        api_key="fake-key",
        base_url=None,
        model="gpt-4o-mini",
        max_tokens=300,
        temperature=0.7,
    )
    assert "gradient descent" in captured["messages"].messages[0].content
    assert callback in captured["config"]["callbacks"].handlers
    attributes.assert_called_once_with(
        tags=["lesson", "recap", "narrative"], trace_name="lesson-recap-narrative"
    )


def test_generate_lesson_recap_narrative_falls_back_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    def fail(_prompt: Any) -> AIMessage:
        message = "LLM unavailable"
        raise RuntimeError(message)

    with (
        patch("news_dashboard.ai_client.get_chat_model", return_value=RunnableLambda(fail)),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        result = generate_lesson_recap_narrative(_make_recap())

    assert "3" in result
