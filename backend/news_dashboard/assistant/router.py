"""HTTP routes for the assistant domain."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from news_dashboard.assistant import service
from news_dashboard.assistant.models import (
    AgentActionPlanRequest,
    AskRequest,
    FeedbackRequest,
)
from news_dashboard.auth import (
    require_auth,
)

router = APIRouter()


@router.post("/api/ask")
def ask_ai(
    payload: AskRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query must not be empty")
    try:
        return service.ask(
            q,
            include_all=payload.include_all,
            user_id=current_user["id"],
            session_id=payload.session_id,
        )
    except service.EmbeddingUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="Ask AI is temporarily unavailable, try again shortly."
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/agent/actions/plan")
def plan_agent_actions(
    payload: AgentActionPlanRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.plan_actions(
            payload.query, user_id=current_user["id"], is_admin=bool(current_user["is_admin"])
        )
    except service.AgentActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/agent/actions/{run_id}/approve")
def approve_agent_action_run(
    run_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.approve_run(
            run_id, user_id=current_user["id"], is_admin=bool(current_user["is_admin"])
        )
    except service.AgentActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.AgentActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/agent/actions/{run_id}/cancel")
def cancel_agent_action_run(
    run_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.cancel_run(run_id, user_id=current_user["id"])
    except service.AgentActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.AgentActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/agent/actions/{run_id}")
def get_agent_action_run(
    run_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.get_run(run_id, user_id=current_user["id"])
    except service.AgentActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/feedback")
def submit_feedback(
    payload: FeedbackRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Record a user's thumbs up/down on an AI answer as a Langfuse score.

    The Langfuse keys stay server-side: the frontend posts the ``trace_id`` it
    received from ``/api/ask`` plus a boolean, and we attach a ``user-thumbs``
    BOOLEAN score to that trace. A no-op (``recorded: False``) when Langfuse is
    disabled, so feedback never errors for the user.
    """
    recorded = service.record_feedback(
        user_id=int(current_user["id"]),
        trace_id=payload.trace_id,
        helpful=payload.helpful,
        comment=payload.comment,
    )
    return {"recorded": recorded}


@router.get("/api/summary")
def summary(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return service.get_user_summary(user_id=current_user["id"])
