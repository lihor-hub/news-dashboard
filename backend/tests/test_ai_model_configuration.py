from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from news_dashboard import ai_client


@pytest.mark.parametrize(
    ("preset", "model", "effort"),
    [
        ("luna-medium", "gpt-6-luna", "medium"),
        ("luna-high", "gpt-6-luna", "high"),
        ("sol-low", "gpt-6-sol", "low"),
        ("sol-medium", "gpt-6-sol", "medium"),
    ],
)
def test_presets_select_requested_model_and_effort(
    monkeypatch: pytest.MonkeyPatch, preset: str, model: str, effort: str
) -> None:
    monkeypatch.setenv("AI_MODEL_PRESET", preset)
    monkeypatch.delenv("OPENAI_QUIZ_MODEL", raising=False)
    monkeypatch.delenv("AI_TEXT_MODEL", raising=False)
    monkeypatch.delenv("AI_REASONING_EFFORT", raising=False)
    selected = ai_client.chat_model_name("OPENAI_QUIZ_MODEL", "gpt-4o-mini")
    assert selected == model
    with patch("langchain_openai.ChatOpenAI", return_value=MagicMock()) as constructor:
        ai_client.get_chat_model(
            api_key="test-key", base_url=None, model=selected, max_tokens=120, temperature=0
        )
    kwargs = constructor.call_args.kwargs
    assert kwargs["use_responses_api"] is True
    assert kwargs["reasoning"] == {"effort": effort}
    assert kwargs["max_tokens"] >= 8192
    assert "temperature" not in kwargs


def test_feature_model_override_wins_over_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODEL_PRESET", "luna-high")
    monkeypatch.setenv("OPENAI_QUIZ_MODEL", "custom-model")
    assert ai_client.chat_model_name("OPENAI_QUIZ_MODEL", "gpt-4o-mini") == "custom-model"


def test_empty_feature_override_uses_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODEL_PRESET", "sol-low")
    monkeypatch.setenv("OPENAI_QUIZ_MODEL", "")
    assert ai_client.chat_model_name("OPENAI_QUIZ_MODEL", "gpt-4o-mini") == "gpt-6-sol"


def test_explicit_openai_provider_does_not_use_gateway_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TEXT_PROVIDER", "openai")
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.setenv("FREE_LLM_BASE_URL", "https://gateway.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "paid-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert ai_client.text_llm_config() == ("paid-key", None)


def test_direct_openai_mode_ignores_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TEXT_PROVIDER", "openai")
    monkeypatch.setenv("FREE_LLM_API_KEY", "gateway-key")
    monkeypatch.setenv("FREE_LLM_BASE_URL", "https://gateway.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "paid-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert ai_client.text_llm_config() == ("paid-key", None)


def test_invalid_preset_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODEL_PRESET", "luna-typo")
    with pytest.raises(ValueError, match="AI_MODEL_PRESET"):
        ai_client.chat_model_name("OPENAI_QUIZ_MODEL", "gpt-4o-mini")


def test_direct_chat_request_uses_reasoning_token_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODEL_PRESET", "luna-high")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    client = MagicMock()
    ai_client.chat_create(
        client, name="ask-ai", model="gpt-6-luna", messages=[], max_tokens=150, temperature=0
    )
    kwargs: dict[str, Any] = client.chat.completions.create.call_args.kwargs
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["max_completion_tokens"] >= 8192
    assert "max_tokens" not in kwargs
    assert "temperature" not in kwargs


def test_ollama_uses_cloud_key_endpoint_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_API_KEY", "test-cloud-key")
    monkeypatch.setenv("AI_MODEL_PRESET", "luna-high")
    monkeypatch.delenv("AI_TEXT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_QUIZ_MODEL", raising=False)
    assert ai_client.text_llm_config() == ("test-cloud-key", "https://ollama.com/v1")
    assert ai_client.chat_model_name("OPENAI_QUIZ_MODEL", "gpt-4o-mini") == "gemma4:31b"


def test_ollama_does_not_fall_back_to_paid_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_core.runnables import RunnableLambda
    from openai import OpenAIError

    monkeypatch.setenv("AI_TEXT_PROVIDER", "ollama")
    monkeypatch.setenv("OPENAI_API_KEY", "unused-paid-key")
    primary = RunnableLambda(lambda _value: (_ for _ in ()).throw(OpenAIError("cloud unavailable")))
    with patch("langchain_openai.ChatOpenAI", return_value=primary) as constructor:
        model = ai_client.get_chat_model(
            api_key="cloud-key", base_url="https://ollama.com/v1", model="gemma4:31b"
        )
        with pytest.raises(OpenAIError, match="cloud unavailable"):
            model.invoke("hello")
    assert constructor.call_count == 1


def test_reasoning_responses_preserve_text_and_json_format(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import httpx2
    from langchain_openai import ChatOpenAI

    monkeypatch.setenv("AI_TEXT_PROVIDER", "openai")
    monkeypatch.setenv("AI_MODEL_PRESET", "luna-high")
    captured: dict[str, Any] = {}

    def handle(request: httpx2.Request) -> httpx2.Response:
        captured.update(json.loads(request.content))
        assert request.url.path == "/v1/responses"
        return httpx2.Response(
            200,
            json={
                "id": "resp-test",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "gpt-6-luna",
                "output": [
                    {
                        "type": "message",
                        "id": "message-test",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": '{"answer":"ok"}', "annotations": []}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 10,
                    "total_tokens": 15,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 5},
                },
            },
        )

    def constructor(**kwargs: Any) -> Any:
        return ChatOpenAI(
            **kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(handle))
        )

    with patch("langchain_openai.ChatOpenAI", side_effect=constructor):
        model = ai_client.get_chat_model(
            api_key="test-key",
            base_url=None,
            model="gpt-6-luna",
            max_tokens=100,
            response_format={"type": "json_object"},
            temperature=0,
        )
        result = model.invoke("Return a JSON answer.")
    assert ai_client.response_text(result) == '{"answer":"ok"}'
    assert captured["reasoning"] == {"effort": "high"}
    assert captured["max_output_tokens"] == 8192
    assert captured["text"]["format"] == {"type": "json_object"}
    assert "temperature" not in captured
