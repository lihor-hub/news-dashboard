from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from news_dashboard.embeddings import (
    DEFAULT_ANSWER_MODEL,
    MissingAICredentialsError,
    _answer,
    _embeddings_ai_config,
    _require_env,
)


def test_require_env_returns_configured_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert _require_env("OPENAI_API_KEY", "generate article embeddings") == "test-key"


def test_require_env_raises_clear_error_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(MissingAICredentialsError, match="Ask AI requires OPENAI_API_KEY"):
        _require_env("OPENAI_API_KEY", "generate article embeddings")


def test_answer_uses_openai_api_key_and_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeMessage:
        content = "answer text"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = (FakeChoice(),)

    class FakeCompletions:
        def create(self, **kwargs: object) -> FakeResponse:
            calls.append(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, api_key: str, **kwargs: Any) -> None:
            calls.append({"api_key": api_key, **kwargs})
            self.chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("FREE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_ANSWER_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    import sys
    from types import SimpleNamespace

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    assert _answer("system", "user") == "answer text"
    assert calls[0] == {"api_key": "test-key", "timeout": 30.0}
    assert calls[1]["model"] == DEFAULT_ANSWER_MODEL


# ── _embeddings_ai_config tests ───────────────────────────────────────────────


def test_embeddings_ai_config_raises_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(MissingAICredentialsError, match="FREE_LLM_API_KEY"):
        _embeddings_ai_config()


def test_embeddings_ai_config_uses_free_llm_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "free-llm-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FREE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    api_key, base_url, _model = _embeddings_ai_config()

    assert api_key == "free-llm-key"
    assert base_url is None


def test_embeddings_ai_config_falls_back_to_shared_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "shared-key")
    monkeypatch.delenv("FREE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    api_key, base_url, _model = _embeddings_ai_config()

    assert api_key == "shared-key"
    assert base_url is None


def test_embeddings_ai_config_uses_free_llm_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("FREE_LLM_BASE_URL", "http://gateway:9130/v1")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    _, base_url, _model = _embeddings_ai_config()

    assert base_url == "http://gateway:9130/v1"


def test_embeddings_ai_config_falls_back_to_shared_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.delenv("FREE_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://shared-gateway:9130/v1")

    _, base_url, _model = _embeddings_ai_config()

    assert base_url == "http://shared-gateway:9130/v1"


def test_embeddings_ai_config_free_llm_base_url_takes_precedence_over_shared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("FREE_LLM_BASE_URL", "http://free-gateway/v1")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://shared-gateway/v1")

    _, base_url, _model = _embeddings_ai_config()

    assert base_url == "http://free-gateway/v1"


def test_embeddings_ai_config_uses_model_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "gateway-embedding-model")

    _, _, model = _embeddings_ai_config()

    assert model == "gateway-embedding-model"


# ── _answer gateway tests ─────────────────────────────────────────────────────


def _make_fake_client() -> MagicMock:
    fake_response = MagicMock()
    fake_response.choices[0].message.content = "answer"
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response
    return fake_client


def test_answer_uses_no_base_url_when_gateway_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-default")
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("FREE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    patch_target = "news_dashboard.ai_client.get_openai_client"
    with patch(patch_target, return_value=_make_fake_client()) as mock_factory:
        _answer("sys", "usr")
    mock_factory.assert_called_once_with(api_key="sk-default", base_url=None)


def test_answer_uses_shared_base_url_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-default")
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("FREE_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://gateway:9130/v1")

    patch_target = "news_dashboard.ai_client.get_openai_client"
    with patch(patch_target, return_value=_make_fake_client()) as mock_factory:
        _answer("sys", "usr")
    mock_factory.assert_called_once_with(api_key="sk-default", base_url="http://gateway:9130/v1")


def test_answer_uses_free_llm_key_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "sk-free-llm")
    monkeypatch.setenv("FREE_LLM_BASE_URL", "http://free-gw:9130/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    patch_target = "news_dashboard.ai_client.get_openai_client"
    with patch(patch_target, return_value=_make_fake_client()) as mock_factory:
        _answer("sys", "usr")
    mock_factory.assert_called_once_with(api_key="sk-free-llm", base_url="http://free-gw:9130/v1")


def test_answer_free_llm_key_takes_precedence_over_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "sk-free-llm")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.delenv("FREE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    patch_target = "news_dashboard.ai_client.get_openai_client"
    with patch(patch_target, return_value=_make_fake_client()) as mock_factory:
        _answer("sys", "usr")
    mock_factory.assert_called_once_with(api_key="sk-free-llm", base_url=None)
