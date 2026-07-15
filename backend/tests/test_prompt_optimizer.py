from __future__ import annotations

from typing import Any, cast
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from news_dashboard.prompt_optimizer import (
    NegativeExample,
    PromptOptimizerError,
    _extract_question,
    _optimizer_ai_config,
    _propose_revision,
    _score_is_negative,
    build_optimizer_prompt,
    collect_negative_examples,
)


@pytest.fixture
def _no_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, True), (0.0, True), ("0", True), (1, False), ("1", False), (None, False), ("x", False)],
)
def test_score_is_negative(value: object, expected: bool) -> None:
    assert _score_is_negative(value) is expected


def test_extract_question_from_dict_and_string() -> None:
    assert _extract_question({"query": " hello ", "include_all": False}) == "hello"
    assert _extract_question("raw question") == "raw question"
    assert _extract_question(None) == ""
    assert _extract_question({"other": "x"}) == ""


def test_build_optimizer_prompt_includes_current_and_examples() -> None:
    examples = [
        NegativeExample(question="Q1", answer="A1", comment="too vague"),
        NegativeExample(question="Q2", answer="A2"),
    ]
    out = build_optimizer_prompt("CURRENT PROMPT TEXT", examples)

    assert "CURRENT PROMPT TEXT" in out
    assert "Q1" in out
    assert "A1" in out
    assert "too vague" in out
    assert "Q2" in out
    assert "A2" in out
    # The example without a comment must not emit a stray "User comment:" line.
    assert out.count("User comment:") == 1


@pytest.mark.usefixtures("_no_langfuse")
def test_collect_negative_examples_requires_langfuse() -> None:
    with pytest.raises(PromptOptimizerError, match="not configured"):
        collect_negative_examples()


def test_optimizer_ai_config_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(PromptOptimizerError, match="API key"):
        _optimizer_ai_config()


def test_optimizer_ai_config_uses_free_llm_key_and_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "free-llm-key")
    monkeypatch.setenv("FREE_LLM_BASE_URL", "http://free-gw/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    api_key, base_url = _optimizer_ai_config()

    assert api_key == "free-llm-key"
    assert base_url == "http://free-gw/v1"


def test_optimizer_ai_config_falls_back_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("FREE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "plain-key")

    api_key, base_url = _optimizer_ai_config()

    assert api_key == "plain-key"
    assert base_url is None


def test_propose_revision_uses_langchain_model_and_preserves_token_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.callbacks import BaseCallbackHandler

    captured: dict[str, object] = {}
    callback = BaseCallbackHandler()

    def invoke(prompt: object, config: object, **_kwargs: object) -> AIMessage:
        captured.update(prompt=prompt, config=config)
        return AIMessage(content="  Revised prompt  ")

    monkeypatch.setattr(
        "news_dashboard.ai_client.get_chat_model",
        lambda **kwargs: captured.update(factory=kwargs) or RunnableLambda(invoke),
    )
    monkeypatch.setattr(
        "news_dashboard.prompt_optimizer._optimizer_ai_config",
        lambda: ("free-key", "https://gateway.example/v1"),
    )
    with (
        monkeypatch.context() as context,
        patch("langfuse.langchain.CallbackHandler", return_value=callback),
        patch("langfuse.propagate_attributes") as attributes,
    ):
        context.setattr("news_dashboard.prompt_optimizer.langfuse_enabled", lambda: True)
        result = _propose_revision(
            "Current", [NegativeExample(question="Q", answer="A")], model="optimizer-model"
        )

    assert result == "Revised prompt"
    assert captured["factory"] == {
        "api_key": "free-key",
        "base_url": "https://gateway.example/v1",
        "model": "optimizer-model",
        "max_tokens": 1024,
    }
    config = cast("dict[str, Any]", captured["config"])
    assert callback in config["callbacks"].handlers
    attributes.assert_called_once_with(tags=["prompt-optimizer"], trace_name="prompt-optimizer")
