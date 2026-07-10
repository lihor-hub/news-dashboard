"""HTTP routes for Learn from Link lessons."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from news_dashboard.auth import require_auth
from news_dashboard.learn_from_link import service
from news_dashboard.learn_from_link.models import (
    LessonCreateRequest,
    LessonQuestionRequest,
    LessonRegenerateRequest,
    LessonSuggestionDismissRequest,
    RelevanceFeedbackRequest,
)

router = APIRouter()


@router.post("/api/learn/lessons", status_code=201)
def create_lesson_endpoint(
    payload: LessonCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        lesson = service.create_lesson(
            current_user["id"],
            payload.url,
            depth=payload.depth,
            persona=payload.persona,
            extract=False,
        )
        background_tasks.add_task(
            service.generate_lesson_from_url,
            int(lesson["id"]),
            current_user["id"],
        )
        return lesson
    except service.LessonUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/learn/lessons")
def list_lessons_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    q: Annotated[str | None, Query(max_length=300)] = None,
    status: Annotated[str | None, Query(pattern="^(pending|complete|failed)$")] = None,
    verdict: Annotated[str | None, Query(pattern="^(skip|skim|read|study)$")] = None,
) -> dict[str, Any]:
    lessons = service.list_lessons(current_user["id"], q=q, status=status, verdict=verdict)
    return {"lessons": lessons}


@router.get("/api/learn/lessons/{lesson_id}")
def get_lesson_endpoint(
    lesson_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    lesson = service.get_lesson(lesson_id, current_user["id"])
    if lesson is None:
        raise HTTPException(status_code=404, detail="lesson not found")
    return lesson


@router.post("/api/learn/lessons/{lesson_id}/podcast")
def generate_lesson_podcast_endpoint(
    lesson_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    force: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    try:
        return service.generate_lesson_podcast(lesson_id, current_user["id"], force=force)
    except service.LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    except service.LessonNotReadyError as exc:
        raise HTTPException(
            status_code=409, detail="lesson must finish generating before creating audio"
        ) from exc
    except service.LessonPodcastNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except service.LessonPodcastGenerationError as exc:
        raise HTTPException(status_code=500, detail="Could not generate podcast audio.") from exc


@router.get("/api/learn/lessons/{lesson_id}/podcast")
def get_lesson_podcast_endpoint(
    lesson_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> FileResponse:
    from news_dashboard.tts import _lesson_podcast_audio_path

    lesson = service.get_lesson(lesson_id, current_user["id"])
    if lesson is None:
        raise HTTPException(status_code=404, detail="lesson not found")

    path = _lesson_podcast_audio_path(lesson_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="podcast audio not generated")
    return FileResponse(path, media_type="audio/mpeg", filename=f"lesson-{lesson_id}-podcast.mp3")


@router.post("/api/learn/lessons/{lesson_id}/slides")
def generate_lesson_slide_deck_endpoint(
    lesson_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    force: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    try:
        return service.generate_lesson_slide_deck(lesson_id, current_user["id"], force=force)
    except service.LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    except service.LessonNotReadyError as exc:
        raise HTTPException(
            status_code=409, detail="lesson must finish generating before creating a slide deck"
        ) from exc
    except service.LessonSlideDeckNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except service.LessonSlideDeckGenerationError as exc:
        raise HTTPException(status_code=500, detail="Could not generate slide deck.") from exc


@router.post("/api/learn/lessons/{lesson_id}/regenerate")
def regenerate_lesson_endpoint(
    lesson_id: int,
    payload: LessonRegenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        lesson = service.regenerate_lesson(
            lesson_id,
            current_user["id"],
            depth=payload.depth,
            persona=payload.persona,
        )
    except service.LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    background_tasks.add_task(
        service.generate_lesson_from_url,
        lesson_id,
        current_user["id"],
    )
    return lesson


@router.get("/api/learn/lessons/{lesson_id}/generations")
def list_lesson_generations_endpoint(
    lesson_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> list[dict[str, Any]]:
    try:
        return service.list_lesson_generations(lesson_id, current_user["id"])
    except service.LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc


@router.post("/api/learn/lessons/{lesson_id}/questions")
def ask_lesson_question_endpoint(
    lesson_id: int,
    payload: LessonQuestionRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        reply = service.ask_lesson_question(
            lesson_id,
            current_user["id"],
            payload.question,
            [{"role": message.role, "content": message.content} for message in payload.history],
        )
    except service.LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc
    except service.LessonQuestionEmptyError as exc:
        raise HTTPException(status_code=400, detail="question must not be blank") from exc
    except service.LessonChatNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"reply": reply}


@router.post("/api/learn/lessons/{lesson_id}/relevance/feedback")
def submit_relevance_feedback_endpoint(
    lesson_id: int,
    payload: RelevanceFeedbackRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.submit_relevance_feedback(
            lesson_id,
            current_user["id"],
            payload.helpful,
        )
    except service.LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lesson not found") from exc


@router.get("/api/learn/suggestions")
def list_lesson_suggestions_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.list_lesson_suggestions(current_user["id"])}


@router.post("/api/learn/suggestions/dismiss")
def dismiss_lesson_suggestion_endpoint(
    payload: LessonSuggestionDismissRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return service.dismiss_lesson_suggestion(current_user["id"], payload.article_id)
