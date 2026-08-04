from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Literal
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from news_dashboard.ai_client import (
    ManagedPrompt,
    _compile_fallback,
    _normalise_host_env,
    chat_create,
    create_score,
    flush,
    get_chat_model,
    get_openai_client,
    get_prompt,
    get_trace_url,
    langfuse_enabled,
    observe,
    response_text,
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


def test_records_final_mcp_result_on_returned_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard import ai_client

    observation = MagicMock()
    client = MagicMock()
    client.start_observation.return_value = observation
    monkeypatch.setattr(ai_client, "langfuse_enabled", lambda: True)
    monkeypatch.setattr(ai_client, "_client", lambda: client)

    ai_client.record_mcp_ask_result(
        "0123456789abcdef0123456789abcdef",
        citation_count=3,
        truncated=True,
        status="ok",
    )

    client.start_observation.assert_called_once_with(
        trace_context={"trace_id": "0123456789abcdef0123456789abcdef"},
        name="mcp-result",
        as_type="span",
        input=None,
        metadata={"surface": "mcp", "operation": "ask-result"},
    )
    observation.end.assert_called_once_with(
        output={"citation_count": 3, "truncated": True, "status": "ok"}
    )


def test_safe_provider_observations_record_primary_failure_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    import openai

    from news_dashboard import ai_client

    failed = MagicMock()
    succeeded = MagicMock()
    escaped: list[BaseException | None] = []

    class CleanExitContext:
        def __init__(self, observation: MagicMock) -> None:
            self.observation = observation

        def __enter__(self) -> MagicMock:
            return self.observation

        def __exit__(
            self, _kind: Any, error: BaseException | None, _traceback: Any
        ) -> Literal[False]:
            escaped.append(error)
            return False

    langfuse = MagicMock()
    langfuse.start_as_current_observation.side_effect = [
        CleanExitContext(failed),
        CleanExitContext(succeeded),
    ]
    primary = MagicMock()
    primary.embeddings.create.side_effect = openai.APIConnectionError(
        request=httpx.Request("POST", "https://provider.invalid")
    )
    response = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.1])],
        usage=SimpleNamespace(prompt_tokens=2, total_tokens=2),
    )
    fallback = MagicMock()
    fallback.embeddings.create.return_value = response
    clients = iter((primary, fallback))
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-secret")
    monkeypatch.setattr(ai_client, "langfuse_enabled", lambda: True)
    monkeypatch.setattr(ai_client, "_client", lambda: langfuse)
    monkeypatch.setattr(ai_client, "get_openai_client", lambda **_kwargs: next(clients))

    client: Any = ai_client.get_chat_client(
        api_key="primary-secret",
        enable_tracing=False,
        safe_observation=ai_client.SafeAIObservation(
            operation="query-embedding", as_type="embedding", model="embed-model"
        ),
    )
    assert client.embeddings.create(model="embed-model", input="PRIVATE") is response

    names = [call.kwargs["name"] for call in langfuse.start_as_current_observation.call_args_list]
    assert names == ["query-embedding-primary", "query-embedding-fallback"]
    assert failed.update.call_args.kwargs["output"] == {"status": "error"}
    assert failed.update.call_args.kwargs["status_message"] == "provider request failed"
    assert succeeded.update.call_args.kwargs["usage_details"] == {"input": 2, "total": 2}
    assert escaped == [None, None]
    rendered = repr((langfuse.mock_calls, failed.mock_calls, succeeded.mock_calls))
    for secret in ("PRIVATE", "primary-secret", "fallback-secret", "provider.invalid"):
        assert secret not in rendered


@pytest.mark.usefixtures("_no_langfuse")
def test_get_prompt_uses_fallback_when_disabled() -> None:
    prompt = get_prompt(
        "ask-system",
        fallback="Answer about {{topic}} clearly.",
        variables={"topic": "Postgres"},
    )
    assert prompt.text == "Answer about Postgres clearly."
    assert prompt.messages is None
    # No Langfuse prompt object to link against in fallback mode.
    assert prompt.langfuse_prompt is None


def test_get_prompt_fetches_production_label_and_keeps_version_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard import ai_client

    remote = MagicMock(is_fallback=False, version=7)
    remote.compile.return_value = "Managed prompt"
    client = MagicMock()
    client.get_prompt.return_value = remote
    monkeypatch.setattr(ai_client, "langfuse_enabled", lambda: True)
    monkeypatch.setattr(ai_client, "_client", lambda: client)

    prompt = get_prompt("managed-prompt", fallback="Fallback")

    client.get_prompt.assert_called_once_with(
        "managed-prompt", label="production", type="text", fallback="Fallback"
    )
    assert prompt.langfuse_prompt is remote


def test_get_prompt_can_fetch_an_exact_version_without_a_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard import ai_client

    remote = MagicMock(is_fallback=False, version=4)
    remote.compile.return_value = "Versioned prompt"
    client = MagicMock()
    client.get_prompt.return_value = remote
    monkeypatch.setattr(ai_client, "langfuse_enabled", lambda: True)
    monkeypatch.setattr(ai_client, "_client", lambda: client)

    prompt = get_prompt("managed-prompt", fallback="Fallback", version=4)

    client.get_prompt.assert_called_once_with(
        "managed-prompt", version=4, type="text", fallback="Fallback"
    )
    assert prompt.langfuse_prompt is remote


@pytest.mark.usefixtures("_no_langfuse")
def test_get_chat_prompt_compiles_local_fallback_in_role_order() -> None:
    prompt = get_prompt(
        "ask-chat",
        fallback=[
            {"role": "system", "content": "Answer about {{topic}}."},
            {"role": "user", "content": "Explain {{topic}} to {{audience}}."},
        ],
        prompt_type="chat",
        variables={"topic": "Postgres", "audience": "beginners"},
    )

    assert prompt.text is None
    assert prompt.messages == [
        {"role": "system", "content": "Answer about Postgres."},
        {"role": "user", "content": "Explain Postgres to beginners."},
    ]
    assert prompt.langfuse_prompt is None


def test_get_text_prompt_fetches_compiles_and_retains_sdk_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    sdk_prompt = MagicMock()
    sdk_prompt.is_fallback = False
    sdk_prompt.compile.return_value = "Answer about Postgres."
    client = MagicMock()
    client.get_prompt.return_value = sdk_prompt

    with patch("news_dashboard.ai_client._client", return_value=client):
        prompt = get_prompt(
            "ask-system",
            fallback="Answer about {{topic}}.",
            variables={"topic": "Postgres"},
        )

    client.get_prompt.assert_called_once_with(
        "ask-system",
        label="production",
        type="text",
        fallback="Answer about {{topic}}.",
    )
    sdk_prompt.compile.assert_called_once_with(topic="Postgres")
    assert prompt.text == "Answer about Postgres."
    assert prompt.messages is None
    assert prompt.langfuse_prompt is sdk_prompt


def test_get_chat_prompt_fetches_compiles_and_retains_sdk_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    fallback = [{"role": "system", "content": "Answer about {{topic}}."}]
    compiled = [{"role": "system", "content": "Answer about Postgres."}]
    sdk_prompt = MagicMock()
    sdk_prompt.is_fallback = False
    sdk_prompt.compile.return_value = compiled
    client = MagicMock()
    client.get_prompt.return_value = sdk_prompt

    with patch("news_dashboard.ai_client._client", return_value=client):
        prompt = get_prompt(
            "ask-chat",
            fallback=fallback,
            prompt_type="chat",
            label="staging",
            variables={"topic": "Postgres"},
        )

    client.get_prompt.assert_called_once_with(
        "ask-chat", label="staging", type="chat", fallback=fallback
    )
    sdk_prompt.compile.assert_called_once_with(topic="Postgres")
    assert prompt.text is None
    assert prompt.messages == compiled
    assert prompt.langfuse_prompt is sdk_prompt


def test_get_prompt_does_not_link_sdk_resolved_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    sdk_prompt = MagicMock()
    sdk_prompt.is_fallback = True
    sdk_prompt.compile.return_value = "Local Postgres"
    client = MagicMock()
    client.get_prompt.return_value = sdk_prompt

    with patch("news_dashboard.ai_client._client", return_value=client):
        prompt = get_prompt("managed", fallback="Local {{topic}}", variables={"topic": "Postgres"})

    assert prompt.text == "Local Postgres"
    assert prompt.langfuse_prompt is None

    chat_create(
        client,
        name="resolved-fallback",
        prompt=prompt,
        model="model",
        messages=[{"role": "user", "content": prompt.text}],
    )
    assert "langfuse_prompt" not in client.chat.completions.create.call_args.kwargs


@pytest.mark.parametrize(
    ("prompt_type", "fallback", "expected_text", "expected_messages"),
    [
        ("text", "Hi {{name}}", "Hi Sam", None),
        (
            "chat",
            [{"role": "assistant", "content": "Hi {{name}}"}],
            None,
            [{"role": "assistant", "content": "Hi Sam"}],
        ),
    ],
)
def test_get_prompt_uses_typed_fallback_when_sdk_raises(
    monkeypatch: pytest.MonkeyPatch,
    prompt_type: str,
    fallback: str | list[dict[str, str]],
    expected_text: str | None,
    expected_messages: list[dict[str, str]] | None,
) -> None:
    from unittest.mock import patch

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    client = MagicMock()
    client.get_prompt.side_effect = RuntimeError("unavailable")
    prompt: ManagedPrompt

    with patch("news_dashboard.ai_client._client", return_value=client):
        if prompt_type == "text":
            assert isinstance(fallback, str)
            prompt = get_prompt(
                "managed", fallback=fallback, prompt_type="text", variables={"name": "Sam"}
            )
        else:
            assert isinstance(fallback, list)
            prompt = get_prompt(
                "managed", fallback=fallback, prompt_type="chat", variables={"name": "Sam"}
            )

    assert prompt.text == expected_text
    assert prompt.messages == expected_messages
    assert prompt.langfuse_prompt is None


def test_get_prompt_warns_and_falls_back_for_invalid_compiled_chat(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from unittest.mock import patch

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    sdk_prompt = MagicMock()
    sdk_prompt.compile.return_value = [{"role": "system"}]
    client = MagicMock()
    client.get_prompt.return_value = sdk_prompt
    fallback = [{"role": "system", "content": "Local {{topic}}"}]

    with patch("news_dashboard.ai_client._client", return_value=client):
        prompt = get_prompt(
            "managed", fallback=fallback, prompt_type="chat", variables={"topic": "copy"}
        )

    assert prompt.messages == [{"role": "system", "content": "Local copy"}]
    assert prompt.langfuse_prompt is None
    assert "using fallback" in caplog.text


def test_get_prompt_warns_and_falls_back_for_invalid_compiled_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from unittest.mock import patch

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    sdk_prompt = MagicMock()
    sdk_prompt.compile.return_value = [{"role": "system", "content": "wrong type"}]
    client = MagicMock()
    client.get_prompt.return_value = sdk_prompt

    with patch("news_dashboard.ai_client._client", return_value=client):
        prompt = get_prompt("managed", fallback="Local {{topic}}", variables={"topic": "copy"})

    assert prompt.text == "Local copy"
    assert prompt.langfuse_prompt is None
    assert "using fallback" in caplog.text


def test_chat_create_forwards_only_real_langfuse_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    client = MagicMock()
    sdk_prompt = object()

    chat_create(
        client,
        name="managed-chat",
        prompt=ManagedPrompt(text=None, messages=[], langfuse_prompt=sdk_prompt),
        model="model",
        messages=[],
    )
    chat_create(
        client,
        name="fallback-chat",
        prompt=ManagedPrompt(text=None, messages=[], langfuse_prompt=None),
        model="model",
        messages=[],
    )

    assert client.chat.completions.create.call_args_list[0].kwargs["langfuse_prompt"] is sdk_prompt
    assert "langfuse_prompt" not in client.chat.completions.create.call_args_list[1].kwargs


@pytest.mark.usefixtures("_no_langfuse")
def test_fetch_metrics_disabled_returns_enabled_false() -> None:
    from news_dashboard.ai_client import fetch_metrics

    assert fetch_metrics(days=30) == {"enabled": False}


def test_compile_fallback_substitutes_double_brace_vars() -> None:
    assert _compile_fallback("Hi {{name}}, {{name}}!", {"name": "Sam"}) == "Hi Sam, Sam!"
    assert _compile_fallback("Hi {{ name }}!", {"name": None}) == "Hi !"
    assert _compile_fallback("no vars here", {}) == "no vars here"


def test_compile_fallback_does_not_compile_placeholders_inside_values() -> None:
    variables = {"first": "{{second}}", "second": "unexpected"}

    assert _compile_fallback("{{first}} / {{missing}}", variables) == "{{second}} / {{missing}}"


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
def test_get_chat_model_forwards_provider_model_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "12.5")

    with patch("langchain_openai.ChatOpenAI", return_value=MagicMock()) as constructor:
        get_chat_model(
            api_key="free-key",
            base_url="http://gateway:9130/v1",
            model="free-model",
        )

    assert constructor.call_args.kwargs == {
        "api_key": "free-key",
        "base_url": "http://gateway:9130/v1",
        "model": "free-model",
        "timeout": 12.5,
    }


def test_response_text_accepts_string_content() -> None:
    assert response_text(AIMessage(content="answer")) == "answer"


def test_response_text_rejects_unsupported_block_content() -> None:
    with pytest.raises(TypeError, match="string content"):
        response_text(AIMessage(content=[{"type": "text", "text": "answer"}]))


@pytest.mark.usefixtures("_no_langfuse")
def test_get_chat_model_preserves_free_provider_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from langchain_core.runnables import RunnableLambda
    from openai import OpenAIError

    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")

    class _UpstreamError(OpenAIError):
        pass

    def fail_primary(_input: object) -> AIMessage:
        message = "gateway down"
        raise _UpstreamError(message)

    primary = RunnableLambda(fail_primary)
    fallback: RunnableLambda[str, AIMessage] = RunnableLambda(
        lambda _input: AIMessage(content="fallback-result")
    )

    with patch("langchain_openai.ChatOpenAI", side_effect=[primary, fallback]) as constructor:
        model = get_chat_model(
            api_key="free-key",
            base_url="http://gateway:9130/v1",
            model="shared-model",
        )
        result = model.invoke("hello")

    assert response_text(result) == "fallback-result"
    assert constructor.call_args_list[1].kwargs == {
        "api_key": "oa-key",
        "model": "shared-model",
        "timeout": 30.0,
    }


@pytest.mark.usefixtures("_no_langfuse")
def test_get_chat_model_preserves_generation_settings_on_lazy_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from langchain_core.runnables import RunnableLambda
    from openai import OpenAIError

    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")

    primary = RunnableLambda(lambda _input: (_ for _ in ()).throw(OpenAIError("gateway down")))
    fallback: RunnableLambda[str, AIMessage] = RunnableLambda(
        lambda _input: AIMessage(content="fallback-result")
    )

    with patch("langchain_openai.ChatOpenAI", side_effect=[primary, fallback]) as constructor:
        model = get_chat_model(
            api_key="free-key",
            base_url="http://gateway:9130/v1",
            model="shared-model",
            max_tokens=60,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        result = model.invoke("hello")

    assert response_text(result) == "fallback-result"
    assert constructor.call_args_list[0].kwargs["max_tokens"] == 60
    assert constructor.call_args_list[0].kwargs["temperature"] == 0.3
    assert constructor.call_args_list[1].kwargs["max_tokens"] == 60
    assert constructor.call_args_list[1].kwargs["temperature"] == 0.3
    assert constructor.call_args_list[0].kwargs["model_kwargs"] == {
        "response_format": {"type": "json_object"}
    }
    assert constructor.call_args_list[1].kwargs["model_kwargs"] == {
        "response_format": {"type": "json_object"}
    }


@pytest.mark.usefixtures("_no_langfuse")
def test_get_chat_model_does_not_construct_fallback_for_healthy_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from langchain_core.runnables import RunnableLambda

    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "invalid-unused-key")
    primary: RunnableLambda[str, AIMessage] = RunnableLambda(
        lambda _input: AIMessage(content="primary-result")
    )

    with patch(
        "langchain_openai.ChatOpenAI",
        side_effect=[primary, RuntimeError("fallback constructed eagerly")],
    ) as constructor:
        model = get_chat_model(api_key="free-key", base_url=None, model="shared-model")
        result = model.invoke("hello")

    assert response_text(result) == "primary-result"
    assert constructor.call_count == 1


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
