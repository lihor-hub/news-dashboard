from __future__ import annotations

import os

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


@pytest.fixture
def _no_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _LANGFUSE_VARS:
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
