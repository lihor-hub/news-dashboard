from __future__ import annotations

import pytest

from news_dashboard.embeddings import MissingAICredentialsError, _require_env


def test_require_env_returns_configured_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert _require_env("OPENAI_API_KEY", "generate article embeddings") == "test-key"


def test_require_env_raises_clear_error_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(MissingAICredentialsError, match="Ask AI requires OPENAI_API_KEY"):
        _require_env("OPENAI_API_KEY", "generate article embeddings")
