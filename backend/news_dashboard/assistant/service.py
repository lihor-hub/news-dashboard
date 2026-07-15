"""Business logic for Ask AI, agent actions, feedback, and summaries."""

from __future__ import annotations

from typing import Any

from news_dashboard.agent_actions import AgentActionError, AgentActionNotFoundError
from news_dashboard.embeddings import EmbeddingUnavailableError


def ask(
    query: str,
    *,
    include_all: bool,
    user_id: int,
    session_id: str | None = None,
) -> dict[str, Any]:
    from news_dashboard.embeddings import ask as ask_impl

    return ask_impl(query, include_all=include_all, user_id=user_id, session_id=session_id)


def plan_actions(query: str, *, user_id: int, is_admin: bool) -> dict[str, Any]:
    from news_dashboard.agent_actions import plan_actions as plan_actions_impl

    return plan_actions_impl(query, user_id=user_id, is_admin=is_admin)


def approve_run(run_id: int, *, user_id: int, is_admin: bool) -> dict[str, Any]:
    from news_dashboard.agent_actions import approve_run as approve_run_impl

    return approve_run_impl(run_id, user_id=user_id, is_admin=is_admin)


def cancel_run(run_id: int, *, user_id: int) -> dict[str, Any]:
    from news_dashboard.agent_actions import cancel_run as cancel_run_impl

    return cancel_run_impl(run_id, user_id=user_id)


def get_run(run_id: int, *, user_id: int) -> dict[str, Any]:
    from news_dashboard.agent_actions import get_run as get_run_impl

    return get_run_impl(run_id, user_id=user_id)


def get_user_summary(*, user_id: int) -> dict[str, Any]:
    from news_dashboard.ingest.service import get_user_summary as get_user_summary_impl

    return get_user_summary_impl(user_id=user_id)


def record_feedback(*, user_id: int, trace_id: str, helpful: bool, comment: str | None) -> bool:
    """Persist feedback in evaluation, memory, and observability stores."""
    from news_dashboard.ai_client import create_score
    from news_dashboard.ai_evals import record_feedback_example
    from news_dashboard.ai_memory.service import record_memory_event

    normalized_comment = (comment or "").strip() or None
    record_feedback_example(
        user_id=user_id,
        trace_id=trace_id,
        helpful=helpful,
        comment=normalized_comment,
    )
    record_memory_event(
        user_id,
        event_type="feedback",
        source="ask_feedback",
        content=normalized_comment or ("helpful" if helpful else "not helpful"),
        metadata={"trace_id": trace_id, "helpful": helpful},
    )
    return create_score(
        trace_id,
        name="user-thumbs",
        value=1 if helpful else 0,
        data_type="BOOLEAN",
        comment=normalized_comment,
    )


__all__ = [
    "AgentActionError",
    "AgentActionNotFoundError",
    "EmbeddingUnavailableError",
    "approve_run",
    "ask",
    "cancel_run",
    "get_run",
    "get_user_summary",
    "plan_actions",
    "record_feedback",
]
