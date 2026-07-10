"""HTTP routes for weekly learning recaps.

Mounted on ``main``'s authenticated ``api`` router, which applies
``require_auth``; handlers still depend on it to receive the current user.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from news_dashboard.auth import require_auth
from news_dashboard.lesson_recaps import service

router = APIRouter()


@router.get("/api/lesson-recaps")
def list_lesson_recaps_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    limit: Annotated[int, Query(ge=1, le=52)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return {"items": service.list_lesson_recaps(current_user["id"], limit=limit, offset=offset)}


@router.get("/api/lesson-recaps/latest")
def get_latest_lesson_recap_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    recap = service.get_latest_lesson_recap(current_user["id"])
    if not recap:
        raise HTTPException(status_code=404, detail="no lesson recap available")
    return recap


@router.post("/api/lesson-recaps/generate")
def generate_lesson_recap_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return service.generate_and_save_weekly_lesson_recap(current_user["id"])


@router.post("/api/lesson-recaps/{recap_id}/podcast")
def generate_lesson_recap_podcast_endpoint(
    recap_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    force: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    try:
        return service.generate_lesson_recap_podcast(recap_id, current_user["id"], force=force)
    except service.LessonRecapNotFoundError as exc:
        raise HTTPException(status_code=404, detail="lesson recap not found") from exc
    except service.LessonRecapPodcastNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except service.LessonRecapPodcastGenerationError as exc:
        raise HTTPException(status_code=500, detail="Could not generate podcast audio.") from exc


@router.get("/api/lesson-recaps/{recap_id}/podcast")
def get_lesson_recap_podcast_endpoint(
    recap_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> FileResponse:
    from news_dashboard.tts import _lesson_recap_audio_path

    recap = service.get_lesson_recap(recap_id, current_user["id"])
    if recap is None:
        raise HTTPException(status_code=404, detail="lesson recap not found")

    path = _lesson_recap_audio_path(recap_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="podcast audio not generated")
    return FileResponse(
        path, media_type="audio/mpeg", filename=f"lesson-recap-{recap_id}-podcast.mp3"
    )
