"""LangChain/LangGraph orchestration adapters for backend AI workflows."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from news_dashboard import ai_client
from news_dashboard.ai_client import ManagedPrompt

T = TypeVar("T")


def _langfuse_callbacks() -> list[Any]:
    """Return Langfuse's LangChain callback handler when tracing is configured."""
    if not ai_client.langfuse_enabled():
        return []
    try:
        from langfuse.langchain import CallbackHandler
    except Exception:
        return []
    return [CallbackHandler()]


def _session_id(name: str, user_id: int | str | None, session_id: str | None) -> str | None:
    if session_id:
        return session_id[:199]
    if user_id is None:
        return None
    return f"{name}:user:{user_id}"[:199]


def invoke_chat_chain(  # noqa: PLR0913 - adapter mirrors provider call metadata.
    *,
    name: str,
    messages: list[dict[str, str]],
    model: str,
    tags: list[str],
    user_id: int | str | None = None,
    session_id: str | None = None,
    prompt: ManagedPrompt | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Invoke a conversational/composable chat flow through vanilla LangChain.

    If LangChain is not importable in a development shell, this preserves the
    previous direct-client behavior. Runtime dependencies include LangChain, so
    production and CI exercise the chain path.
    """
    api_key, base_url = ai_client.free_llm_config()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format

    if not ai_client.langfuse_enabled():
        client = ai_client.get_chat_client(api_key=api_key, base_url=base_url)
        response = ai_client.chat_create(
            client,
            name=name,
            tags=tags,
            user_id=user_id,
            session_id=session_id,
            prompt=prompt,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    try:
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
        )
        from langchain_openai import ChatOpenAI
        from langfuse import propagate_attributes
    except Exception:
        client = ai_client.get_chat_client(api_key=api_key, base_url=base_url)
        response = ai_client.chat_create(
            client,
            name=name,
            tags=tags,
            user_id=user_id,
            session_id=session_id,
            prompt=prompt,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    chain_messages: list[Any] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "system":
            chain_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            chain_messages.append(AIMessage(content=content))
        else:
            chain_messages.append(HumanMessage(content=content))

    llm_kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "timeout": ai_client.request_timeout_seconds(),
    }
    if base_url is not None:
        llm_kwargs["base_url"] = base_url
    if max_tokens is not None:
        llm_kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        llm_kwargs["model_kwargs"] = {"response_format": response_format}
    llm = ChatOpenAI(**llm_kwargs)

    config: dict[str, Any] = {
        "callbacks": _langfuse_callbacks(),
        "metadata": {
            "langfuse_tags": tags,
            "langfuse_user_id": str(user_id) if user_id is not None else None,
            "langfuse_session_id": _session_id(name, user_id, session_id),
            "langfuse_prompt": prompt.langfuse_prompt if prompt else None,
        },
        "run_name": name,
    }
    config["metadata"] = {k: v for k, v in config["metadata"].items() if v is not None}
    with propagate_attributes(
        user_id=str(user_id) if user_id is not None else None,
        session_id=_session_id(name, user_id, session_id),
        tags=tags,
    ):
        result = llm.invoke(chain_messages, config=cast("Any", config))
    return str(result.content or "")


def run_workflow_graph(
    *,
    name: str,
    initial_state: dict[str, Any],
    node: Callable[[dict[str, Any]], dict[str, Any]],
    user_id: int | str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Run one workflow node through LangGraph while preserving exceptions."""
    try:
        from langfuse import propagate_attributes
        from langgraph.graph import END, StateGraph
    except Exception:
        return node(initial_state)

    state_graph = cast("Any", StateGraph)
    graph = state_graph(dict[str, Any])
    graph.add_node(name, cast("Any", node))
    graph.set_entry_point(name)
    graph.add_edge(name, END)
    app = graph.compile()
    with propagate_attributes(
        user_id=str(user_id) if user_id is not None else None,
        session_id=_session_id(name, user_id, session_id),
        tags=["workflow", name],
    ):
        result = app.invoke(cast("Any", initial_state))
    return cast("dict[str, Any]", result)
