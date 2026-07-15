from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from news_dashboard import ai_client, ai_orchestration


def test_invoke_chat_chain_uses_direct_client_when_tracing_disabled(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_chat_create(_client: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="direct answer"))]
        )

    monkeypatch.setenv("FREE_LLM_API_KEY", "test-key")
    monkeypatch.setattr(ai_client, "langfuse_enabled", lambda: False)
    monkeypatch.setattr(ai_client, "get_chat_client", lambda **_kwargs: object())
    monkeypatch.setattr(ai_client, "chat_create", fake_chat_create)

    answer = ai_orchestration.invoke_chat_chain(
        name="ask-ai",
        tags=["ask-ai"],
        user_id=42,
        session_id="ask-session-1",
        model="gpt-test",
        messages=[{"role": "user", "content": "question"}],
    )

    assert answer == "direct answer"
    assert captured["name"] == "ask-ai"
    assert captured["user_id"] == 42
    assert captured["session_id"] == "ask-session-1"


def test_invoke_chat_chain_propagates_langfuse_session_metadata(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class FakeMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured["llm_kwargs"] = kwargs

        def invoke(self, messages: list[Any], config: dict[str, Any]) -> Any:
            captured["messages"] = messages
            captured["config"] = config
            return SimpleNamespace(content="chain answer")

    class FakePropagate:
        def __init__(self, **kwargs: Any) -> None:
            captured["propagate"] = kwargs

        def __enter__(self) -> None:
            return None

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setenv("FREE_LLM_API_KEY", "test-key")
    monkeypatch.setattr(ai_client, "langfuse_enabled", lambda: True)
    monkeypatch.setattr(ai_orchestration, "_langfuse_callbacks", lambda: ["callback"])
    monkeypatch.setitem(
        __import__("sys").modules,
        "langchain_core.messages",
        SimpleNamespace(
            AIMessage=FakeMessage,
            HumanMessage=FakeMessage,
            SystemMessage=FakeMessage,
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=FakeChatOpenAI),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "langfuse",
        SimpleNamespace(propagate_attributes=FakePropagate),
    )

    answer = ai_orchestration.invoke_chat_chain(
        name="briefing-chat",
        tags=["briefing", "chat"],
        user_id=7,
        session_id="briefing:3:user:7",
        model="gpt-test",
        messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "question"},
        ],
    )

    assert answer == "chain answer"
    assert captured["config"]["callbacks"] == ["callback"]
    assert captured["config"]["metadata"]["langfuse_user_id"] == "7"
    assert captured["config"]["metadata"]["langfuse_session_id"] == "briefing:3:user:7"
    assert captured["propagate"]["user_id"] == "7"
    assert captured["propagate"]["session_id"] == "briefing:3:user:7"
    assert captured["propagate"]["tags"] == ["briefing", "chat"]


def test_run_workflow_graph_preserves_node_result(monkeypatch: Any) -> None:
    monkeypatch.setitem(
        __import__("sys").modules,
        "langfuse",
        SimpleNamespace(propagate_attributes=lambda **_kwargs: _NullContext()),
    )

    result = ai_orchestration.run_workflow_graph(
        name="lesson-workflow",
        initial_state={"step": "extract"},
        node=lambda state: {**state, "status": "complete"},
        user_id=3,
    )

    assert result["step"] == "extract"
    assert result["status"] == "complete"


class _NullContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None
