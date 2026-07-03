from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from news_dashboard.ai_memory import service
from news_dashboard.ai_memory.models import MemoryCreateRequest, MemoryUpdateRequest
from news_dashboard.auth import require_auth

router = APIRouter()


@router.get("/api/users/me/ai-memories")
def list_ai_memories(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.list_memories(int(current_user["id"]), include_inactive=True)}


@router.post("/api/users/me/ai-memories")
def create_ai_memory(
    payload: MemoryCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.create_memory(
            int(current_user["id"]),
            payload.content,
            memory_type=payload.memory_type,
            source=payload.source,
            confidence=payload.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/api/users/me/ai-memories/{memory_id}")
def update_ai_memory(
    memory_id: int,
    payload: MemoryUpdateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        memory = service.update_memory(
            int(current_user["id"]),
            memory_id,
            content=payload.content,
            memory_type=payload.memory_type,
            confidence=payload.confidence,
            active=payload.active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if memory is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return memory


@router.delete("/api/users/me/ai-memories/{memory_id}")
def deactivate_ai_memory(
    memory_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    memory = service.update_memory(int(current_user["id"]), memory_id, active=False)
    if memory is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return memory


@router.post("/api/users/me/ai-memories/learn-from-reading")
def learn_ai_memories_from_reading(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return service.learn_from_recent_reading(int(current_user["id"]))
