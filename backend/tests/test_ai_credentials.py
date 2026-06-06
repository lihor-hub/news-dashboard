from __future__ import annotations

import pytest

from news_dashboard.embeddings import (
    DEFAULT_ANSWER_MODEL,
    MissingAICredentialsError,
    _answer,
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
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs: object) -> FakeResponse:
            calls.append(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            calls.append({"api_key": api_key})
            self.chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_ANSWER_MODEL", raising=False)
    import sys
    from types import SimpleNamespace

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    assert _answer("system", "user") == "answer text"
    assert calls[0] == {"api_key": "test-key"}
    assert calls[1]["model"] == DEFAULT_ANSWER_MODEL
