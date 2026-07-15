"""Tests for the AI weekly recap narrative generator."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

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
    monkeypatch.setenv("OPENAI_BRIEFING_MODEL", "gpt-4o-mini")

    narrative_text = (
        "You had a strong week, reading 12 articles mostly about science.\n\n"
        "Keep up the streak — three days running is great momentum."
    )
    captured: dict[str, Any] = {}

    def fake_invoke(messages: Any, config: Any, **_kwargs: Any) -> AIMessage:
        captured.update(messages=messages, config=config)
        return AIMessage(content=narrative_text)

    with (
        patch(
            "news_dashboard.ai_client.get_chat_model",
            return_value=RunnableLambda(fake_invoke),
        ) as factory,
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        result = generate_recap_narrative(_make_recap())

    assert result == narrative_text
    factory.assert_called_once_with(
        api_key="fake-key",
        base_url=None,
        model="gpt-4o-mini",
        max_tokens=300,
        temperature=0.7,
    )
    assert "12" in captured["messages"].messages[0].content
    assert captured["config"]["callbacks"] is not None


def test_generate_recap_narrative_falls_back_on_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    def fail(_prompt: Any) -> AIMessage:
        message = "LLM unavailable"
        raise RuntimeError(message)

    with (
        patch("news_dashboard.ai_client.get_chat_model", return_value=RunnableLambda(fail)),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        result = generate_recap_narrative(_make_recap())

    assert "12" in result


def test_generate_recap_narrative_mentions_saved_and_dwell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    captured_prompt: list[str] = []

    def fake_invoke(prompt: Any, **_kwargs: Any) -> AIMessage:
        captured_prompt.append(prompt.messages[0].content)
        return AIMessage(content="Narrative.")

    recap = _make_recap(
        saved={"starred_this_week": 2, "read_from_backlog": 1, "backlog_total": 8},
        dwell={"skims": 3, "reads": 9, "average_seconds": 42.0},
    )

    with (
        patch(
            "news_dashboard.ai_client.get_chat_model",
            return_value=RunnableLambda(fake_invoke),
        ),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        generate_recap_narrative(recap)

    prompt = captured_prompt[0]
    assert "backlog_total" in prompt
    assert "average_seconds" in prompt
    assert "generated_at" not in prompt
