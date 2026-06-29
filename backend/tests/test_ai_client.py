from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from news_dashboard.ai_client import (
    _compile_fallback,
    _normalise_host_env,
    create_score,
    flush,
    get_openai_client,
    get_prompt,
    get_trace_url,
    langfuse_enabled,
    observe,
    trace_params,
)

_LANGFUSE_VARS = (
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
    "LANGFUSE_BASE_URL",
)
_AI_TIMEOUT_VARS = ("AI_REQUEST_TIMEOUT_SECONDS", "AI_TTS_TIMEOUT_SECONDS")


@pytest.fixture
def _no_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _LANGFUSE_VARS:
        monkeypatch.delenv(var, raising=False)
    for var in _AI_TIMEOUT_VARS:
        monkeypatch.delenv(var, raising=False)


def test_langfuse_enabled_requires_both_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    assert langfuse_enabled() is False

    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    assert langfuse_enabled() is True


@pytest.mark.usefixtures("_no_langfuse")
def test_returns_plain_openai_client_when_tracing_disabled() -> None:
    from openai import OpenAI

    client = get_openai_client(api_key="test-key")

    # Plain SDK client, not the Langfuse subclass.
    assert type(client) is OpenAI
    assert client.api_key == "test-key"


@pytest.mark.usefixtures("_no_langfuse")
def test_base_url_is_forwarded() -> None:
    client = get_openai_client(api_key="test-key", base_url="http://gateway:9130/v1")

    assert str(client.base_url).rstrip("/") == "http://gateway:9130/v1"


@pytest.mark.usefixtures("_no_langfuse")
def test_plain_openai_client_uses_configured_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    import openai

    monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "12.5")

    with patch.object(openai, "OpenAI", return_value=MagicMock()) as constructor:
        get_openai_client(api_key="test-key")

    assert constructor.call_args.kwargs["timeout"] == 12.5


@pytest.mark.usefixtures("_no_langfuse")
def test_plain_openai_client_accepts_explicit_timeout_override() -> None:
    from unittest.mock import patch

    import openai

    with patch.object(openai, "OpenAI", return_value=MagicMock()) as constructor:
        get_openai_client(api_key="test-key", timeout_seconds=90.0)

    assert constructor.call_args.kwargs["timeout"] == 90.0


def test_returns_langfuse_client_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # The wrapped client requires the langfuse SDK; skip when it is not importable
    # in this interpreter (e.g. a system pytest outside the project venv). It is a
    # core dependency, so this still runs in CI and any properly-synced env.
    pytest.importorskip("langfuse.openai")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse:3000")

    client = get_openai_client(api_key="test-key")

    # Langfuse traces by wrapping the OpenAI SDK methods (wrapt), rather than
    # subclassing — a wrapt wrapper exposes the original via __wrapped__.
    assert hasattr(client.chat.completions.create, "__wrapped__")


def test_langfuse_client_uses_configured_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    wrapped_openai = MagicMock(return_value=MagicMock())
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "17")

    with patch(
        "news_dashboard.ai_client.importlib.import_module",
        return_value=SimpleNamespace(OpenAI=wrapped_openai),
    ):
        get_openai_client(api_key="test-key", base_url="http://gateway:9130/v1")

    assert wrapped_openai.call_args.kwargs == {
        "api_key": "test-key",
        "base_url": "http://gateway:9130/v1",
        "timeout": 17.0,
    }


def test_tts_timeout_uses_separate_default_and_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.ai_client import tts_timeout_seconds

    monkeypatch.delenv("AI_TTS_TIMEOUT_SECONDS", raising=False)
    assert tts_timeout_seconds() == 120.0

    monkeypatch.setenv("AI_TTS_TIMEOUT_SECONDS", "240")
    assert tts_timeout_seconds() == 240.0


@pytest.mark.usefixtures("_no_langfuse")
def test_flush_is_noop_without_credentials() -> None:
    # Must not raise when tracing is disabled.
    flush()


@pytest.mark.usefixtures("_no_langfuse")
def test_trace_params_empty_when_disabled() -> None:
    # The plain OpenAI client rejects unknown kwargs, so nothing must leak.
    assert trace_params("ask-ai", tags=["ask-ai"]) == {}


def test_trace_params_sets_name_and_tags_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")

    assert trace_params("briefing-generation", tags=["briefing"]) == {
        "name": "briefing-generation",
        "metadata": {"langfuse_tags": ["briefing"]},
    }
    assert trace_params("ask-ai") == {"name": "ask-ai"}


def test_trace_params_includes_user_and_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")

    assert trace_params("ask-ai", user_id=42, session_id="sess-1") == {
        "name": "ask-ai",
        "metadata": {"langfuse_user_id": "42", "langfuse_session_id": "sess-1"},
    }


@pytest.mark.usefixtures("_no_langfuse")
def test_base_url_alias_populates_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://fuse.example.com")
    _normalise_host_env()
    assert os.environ["LANGFUSE_HOST"] == "https://fuse.example.com"


def test_existing_host_not_overwritten_by_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", "https://primary.example.com")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://alias.example.com")
    _normalise_host_env()
    assert os.environ["LANGFUSE_HOST"] == "https://primary.example.com"


@pytest.mark.usefixtures("_no_langfuse")
def test_observe_is_noop_without_credentials() -> None:
    # Disabled: yields a handle with no trace id and tolerates update_output.
    with observe("ask-ai-pipeline", input={"q": "hi"}) as handle:
        assert handle.trace_id is None
        handle.update_output("answer")


@pytest.mark.usefixtures("_no_langfuse")
def test_create_score_and_trace_url_noop_without_credentials() -> None:
    assert create_score("trace-1", name="user-thumbs", value=1, data_type="BOOLEAN") is False
    assert get_trace_url("trace-1") is None


@pytest.mark.usefixtures("_no_langfuse")
def test_get_prompt_uses_fallback_when_disabled() -> None:
    prompt = get_prompt(
        "ask-system",
        fallback="Answer about {{topic}} clearly.",
        variables={"topic": "Postgres"},
    )
    assert prompt.text == "Answer about Postgres clearly."
    # No Langfuse prompt object to link against in fallback mode.
    assert prompt.langfuse_prompt is None


@pytest.mark.usefixtures("_no_langfuse")
def test_fetch_metrics_disabled_returns_enabled_false() -> None:
    from news_dashboard.ai_client import fetch_metrics

    assert fetch_metrics(days=30) == {"enabled": False}


def test_compile_fallback_substitutes_double_brace_vars() -> None:
    assert _compile_fallback("Hi {{name}}, {{name}}!", {"name": "Sam"}) == "Hi Sam, Sam!"
    assert _compile_fallback("no vars here", {}) == "no vars here"


# ── get_chat_client runtime free-LLM→OpenAI fallback ───────────────────────


def _raising_client(exc: Exception) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.side_effect = exc
    client.embeddings.create.side_effect = exc
    return client


def _ok_client(result: object) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value = result
    client.embeddings.create.return_value = result
    return client


def _clear_ai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("FREE_LLM_API_KEY", "FREE_LLM_BASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.usefixtures("_no_langfuse")
def test_get_chat_client_falls_back_to_openai_on_chat_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from openai import OpenAIError

    from news_dashboard.ai_client import get_chat_client

    class _UpstreamError(OpenAIError):
        pass

    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("FREE_LLM_API_KEY", "free-key")
    monkeypatch.setenv("FREE_LLM_BASE_URL", "http://gw/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")

    primary = _raising_client(_UpstreamError("gateway down"))
    fallback = _ok_client("fallback-result")
    with patch(
        "news_dashboard.ai_client.get_openai_client", side_effect=[primary, fallback]
    ) as factory:
        client = get_chat_client(api_key="free-key", base_url="http://gw/v1")
        result: object = client.chat.completions.create(model="m", messages=[])

    assert result == "fallback-result"
    assert factory.call_args_list[0].kwargs == {"api_key": "free-key", "base_url": "http://gw/v1"}
    assert factory.call_args_list[1].kwargs == {"api_key": "oa-key", "base_url": None}


@pytest.mark.usefixtures("_no_langfuse")
def test_get_chat_client_falls_back_to_openai_on_embedding_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from openai import OpenAIError

    from news_dashboard.ai_client import get_chat_client

    class _UpstreamError(OpenAIError):
        pass

    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("FREE_LLM_API_KEY", "free-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")

    primary = _raising_client(_UpstreamError("gateway down"))
    fallback = _ok_client("embedding-result")
    with patch(
        "news_dashboard.ai_client.get_openai_client", side_effect=[primary, fallback]
    ) as factory:
        client = get_chat_client(api_key="free-key", base_url=None)
        result: object = client.embeddings.create(model="m", input="x")

    assert result == "embedding-result"
    assert factory.call_count == 2


@pytest.mark.usefixtures("_no_langfuse")
def test_get_chat_client_no_fallback_when_single_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from openai import OpenAIError

    from news_dashboard.ai_client import get_chat_client

    class _UpstreamError(OpenAIError):
        pass

    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")

    primary = _raising_client(_UpstreamError("boom"))
    with patch("news_dashboard.ai_client.get_openai_client", side_effect=[primary]) as factory:
        client = get_chat_client(api_key="oa-key", base_url=None)
        with pytest.raises(OpenAIError):
            client.chat.completions.create(model="m", messages=[])

    assert factory.call_count == 1


@pytest.mark.usefixtures("_no_langfuse")
def test_get_chat_client_no_fallback_when_openai_key_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from openai import OpenAIError

    from news_dashboard.ai_client import get_chat_client

    class _UpstreamError(OpenAIError):
        pass

    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("FREE_LLM_API_KEY", "free-key")

    primary = _raising_client(_UpstreamError("boom"))
    with patch("news_dashboard.ai_client.get_openai_client", side_effect=[primary]) as factory:
        client = get_chat_client(api_key="free-key", base_url=None)
        with pytest.raises(OpenAIError):
            client.chat.completions.create(model="m", messages=[])

    assert factory.call_count == 1


@pytest.mark.usefixtures("_no_langfuse")
def test_get_chat_client_happy_path_builds_one_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from news_dashboard.ai_client import get_chat_client

    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("FREE_LLM_API_KEY", "free-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")

    primary = _ok_client("primary-result")
    # Only one client provided: if the fallback were built eagerly, StopIteration would raise.
    with patch("news_dashboard.ai_client.get_openai_client", side_effect=[primary]) as factory:
        client = get_chat_client(api_key="free-key", base_url=None)
        result: object = client.chat.completions.create(model="m", messages=[])

    assert result == "primary-result"
    assert factory.call_count == 1
