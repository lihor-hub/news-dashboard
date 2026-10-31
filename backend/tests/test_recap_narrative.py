"""Tests for the AI weekly recap narrative generator."""

from __future__ import annotations

import json
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
        snapshot_version=2,
        progress={"rewards": [{"key": "PRIVATE_TOPIC_REWARD"}], "coverage": "PRIVATE_COVERAGE"},
        period={"timezone": "PRIVATE_ZONE"},
        unexpected_future_field="PRIVATE_FUTURE",
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
    assert "PRIVATE_" not in prompt
    assert '"progress"' not in prompt
    assert '"period"' not in prompt


@pytest.mark.parametrize("container", [{"private": "PRIVATE_SCALAR"}, ["PRIVATE_SCALAR"]])
def test_generate_recap_narrative_projects_legacy_leaves_before_model_and_tracing(
    container: object,
) -> None:
    from langchain_core.callbacks import BaseCallbackHandler

    traced_inputs: list[str] = []
    prompts: list[str] = []

    class CaptureTrace(BaseCallbackHandler):
        def on_chain_start(self, serialized: Any, inputs: Any, **_kwargs: Any) -> None:
            del serialized
            traced_inputs.append(str(inputs))

    def invoke(prompt: Any) -> AIMessage:
        prompts.append(prompt.messages[0].content)
        return AIMessage(content="Narrative.")

    recap = _make_recap(
        categories=[
            {"category": "science", "count": 5, "topic_provenance": "PRIVATE_CATEGORY"},
            {"category": container, "count": container},
            container,
        ],
        sources=[
            {"source": "Example News", "count": 4, "coverage": "PRIVATE_SOURCE"},
            {"source": container, "count": container},
            container,
        ],
        saved={
            "starred_this_week": 2,
            "read_from_backlog": 1,
            "backlog_total": container,
            "progress": "PRIVATE_SAVED",
        },
        dwell={
            "skims": 3,
            "reads": 9,
            "average_seconds": container,
            "coverage": "PRIVATE_DWELL",
        },
        nudges=[
            {
                "id": "source:example",
                "kind": "source",
                "title": "Noisy source",
                "message": "Try another source.",
                "reason": "low_signal",
                "skip_rate": 0.9,
                "articles_last_30_days": 50,
                "action": "disable_source",
                "target": "example",
                "target_label": "Example News",
                "progress": "PRIVATE_NUDGE",
            },
            {"message": container, "skip_rate": container},
            container,
        ],
        week_start=container,
        minutes_read=container,
        progress={"private": "PRIVATE_PROGRESS"},
    )
    with (
        patch("news_dashboard.ai_client.get_chat_model", return_value=RunnableLambda(invoke)),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
        patch("news_dashboard.ai_client.langfuse_enabled", return_value=True),
        patch("langfuse.langchain.CallbackHandler", return_value=CaptureTrace()),
    ):
        assert generate_recap_narrative(recap) == "Narrative."

    assert len(prompts) == 1
    assert traced_inputs
    assert all("PRIVATE_" not in value for value in [*prompts, *traced_inputs])
    metrics = json.loads(prompts[0].split("Recap metrics (JSON):\n")[1].split("\n\n")[0])
    assert "week_start" not in metrics
    assert "minutes_read" not in metrics
    assert metrics["articles_read"] == 12
    assert metrics["categories"][0] == {"category": "science", "count": 5}
    assert metrics["sources"][0] == {"source": "Example News", "count": 4}
    assert metrics["saved"] == {"starred_this_week": 2, "read_from_backlog": 1}
    assert metrics["dwell"] == {"skims": 3, "reads": 9}
    assert metrics["nudges"][0] == {
        "id": "source:example",
        "kind": "source",
        "title": "Noisy source",
        "message": "Try another source.",
        "reason": "low_signal",
        "skip_rate": 0.9,
        "articles_last_30_days": 50,
        "action": "disable_source",
        "target": "example",
        "target_label": "Example News",
    }


def test_generate_recap_narrative_traces_callback_attribution_and_literal_braces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.callbacks import BaseCallbackHandler

    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")
    callback = BaseCallbackHandler()
    captured: dict[str, Any] = {}

    def invoke(prompt: Any, config: Any) -> AIMessage:
        captured.update(prompt=prompt, config=config)
        return AIMessage(content="Narrative.")

    with (
        patch(
            "news_dashboard.ai_client.get_chat_model",
            return_value=RunnableLambda(invoke),
        ),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
        patch("news_dashboard.ai_client.langfuse_enabled", return_value=True),
        patch("langfuse.langchain.CallbackHandler", return_value=callback),
        patch("langfuse.propagate_attributes") as attributes,
    ):
        result = generate_recap_narrative(_make_recap(categories=[{"category": "{science}"}]))

    assert result == "Narrative."
    assert callback in captured["config"]["callbacks"].handlers
    attributes.assert_called_once_with(tags=["recap", "narrative"], trace_name="recap-narrative")
    assert "{science}" in captured["prompt"].messages[0].content
