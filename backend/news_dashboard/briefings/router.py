"""HTTP routes for the briefings domain."""

from __future__ import annotations

import logging
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import FileResponse

from news_dashboard.auth import (
    require_auth,
)
from news_dashboard.briefings.models import (
    BriefingChatRequest,
    BriefingCreateRequest,
)
from news_dashboard.briefings.service import (
    BriefingAINotConfiguredError,
    BriefingGenerationError,
    BriefingNotFoundError,
    chat_with_briefing,
    generate_briefing,
    get_briefing,
    get_latest_briefing,
    list_briefings,
)

router = APIRouter()
public_router = APIRouter()
logger = logging.getLogger(__name__)


def _request_base_origin(request: Request) -> str:
    """Return the externally visible request origin when proxy headers exist."""
    forwarded_host = request.headers.get("x-forwarded-host")
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_host and forwarded_proto:
        host = forwarded_host.split(",", maxsplit=1)[0].strip()
        proto = forwarded_proto.split(",", maxsplit=1)[0].strip()
        if host and proto:
            return f"{proto}://{host}"
    parts = urlsplit(str(request.url))
    return f"{parts.scheme}://{parts.netloc}"


@router.get("/api/briefings/latest")
def briefings_latest(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    briefing = get_latest_briefing(user_id=current_user["id"])
    if briefing is None:
        return {"status": "empty"}
    return briefing


@router.get("/api/briefings")
def briefings_list(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return {"items": list_briefings(limit=limit, offset=offset, user_id=current_user["id"])}


@router.get("/api/briefings/podcast-feed-token")
def get_podcast_feed_token_endpoint(
    request: Request,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, str]:
    """Return the user's current (revocable) podcast feed token and subscribe URL."""
    from news_dashboard.auth import get_podcast_feed_token_version
    from news_dashboard.podcast_feed import feed_url, make_feed_token

    version = get_podcast_feed_token_version(current_user["id"])
    if version is None:
        raise HTTPException(status_code=404, detail="user not found")
    token = make_feed_token(current_user["id"], version)
    return {"token": token, "url": feed_url(token, _request_base_origin(request))}


@router.post("/api/briefings/podcast-feed-token/regenerate")
def regenerate_podcast_feed_token_endpoint(
    request: Request,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, str]:
    """Revoke the user's current podcast feed token and issue a new one."""
    from news_dashboard.auth import bump_podcast_feed_token_version
    from news_dashboard.podcast_feed import feed_url, make_feed_token

    version = bump_podcast_feed_token_version(current_user["id"])
    token = make_feed_token(current_user["id"], version)
    return {"token": token, "url": feed_url(token, _request_base_origin(request))}


@public_router.get("/api/briefings/podcast.rss")
def podcast_rss_feed_endpoint(request: Request, token: Annotated[str, Query()]) -> Response:
    """Serve the authenticated user's podcast feed of previously-generated briefs.

    Authenticated via a revocable per-user token (not the session cookie), since
    podcast clients cannot perform an interactive login.
    """
    from news_dashboard.briefings.service import list_briefings_with_script
    from news_dashboard.podcast_feed import build_feed_xml, verify_feed_token
    from news_dashboard.tts import (
        TTSNotConfiguredError,
        _podcast_audio_path,
        generate_podcast_audio,
    )

    user_id = verify_feed_token(token)
    if user_id is None:
        raise HTTPException(status_code=403, detail="invalid or revoked podcast feed token")

    briefings = list_briefings_with_script(user_id=user_id)
    episodes = []
    for briefing in briefings:
        audio_path = _podcast_audio_path(briefing["id"])
        if not audio_path.exists():
            try:
                generate_podcast_audio(briefing["id"], briefing["script"])
            except (TTSNotConfiguredError, ValueError) as exc:
                logger.warning(
                    "Skipping podcast feed episode for briefing %d: %s", briefing["id"], exc
                )
                continue
        briefing["audio_bytes"] = audio_path.stat().st_size
        episodes.append(briefing)

    xml = build_feed_xml(token=token, briefings=episodes, base_url=_request_base_origin(request))
    return Response(content=xml, media_type="application/rss+xml")


@router.get("/api/briefings/{briefing_id}")
def briefings_detail(
    briefing_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    briefing = get_briefing(briefing_id, user_id=current_user["id"])
    if briefing is None:
        raise HTTPException(status_code=404, detail="briefing not found")
    return briefing


@router.post("/api/briefings/{briefing_id}/podcast")
def generate_podcast_endpoint(
    briefing_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, str]:
    from news_dashboard.briefings.service import update_briefing_script
    from news_dashboard.tts import (
        TTSNotConfiguredError,
        _podcast_audio_path,
        generate_podcast_audio,
        generate_podcast_script,
    )

    briefing = get_briefing(briefing_id, user_id=current_user["id"])
    if not briefing:
        raise HTTPException(status_code=404, detail="briefing not found")

    audio_path = _podcast_audio_path(briefing_id)
    if not audio_path.exists():
        script = briefing.get("script")
        if not script:
            content_dict = {
                "title": briefing.get("title", ""),
                "summary": briefing.get("summary", ""),
                "sections": briefing.get("content", {}).get("sections", []),
            }
            try:
                script = generate_podcast_script(content_dict)
                update_briefing_script(briefing_id, script)
            except TTSNotConfiguredError as exc:
                raise HTTPException(status_code=501, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"Failed to generate podcast script: {exc}"
                ) from exc

        try:
            generate_podcast_audio(briefing_id, script)
        except TTSNotConfiguredError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"url": f"/api/briefings/{briefing_id}/podcast"}


@router.get("/api/briefings/{briefing_id}/podcast")
def get_podcast_audio_endpoint(
    briefing_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> FileResponse:
    from news_dashboard.tts import _podcast_audio_path

    briefing = get_briefing(briefing_id, user_id=current_user["id"])
    if not briefing:
        raise HTTPException(status_code=404, detail="briefing not found")

    audio_path = _podcast_audio_path(briefing_id)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="podcast audio file not found")

    return FileResponse(audio_path, media_type="audio/mpeg", filename=f"podcast-{briefing_id}.mp3")


@public_router.get("/api/briefings/{briefing_id}/podcast-audio")
def get_podcast_audio_by_token_endpoint(
    briefing_id: int,
    token: Annotated[str, Query()],
) -> FileResponse:
    """Serve podcast episode audio for a podcast-client feed subscription (token auth)."""
    from news_dashboard.podcast_feed import verify_feed_token
    from news_dashboard.tts import _podcast_audio_path

    user_id = verify_feed_token(token)
    if user_id is None:
        raise HTTPException(status_code=403, detail="invalid or revoked podcast feed token")

    briefing = get_briefing(briefing_id, user_id=user_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="briefing not found")

    audio_path = _podcast_audio_path(briefing_id)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="podcast audio file not found")

    return FileResponse(audio_path, media_type="audio/mpeg", filename=f"podcast-{briefing_id}.mp3")


@router.post("/api/briefings")
def briefings_create(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: BriefingCreateRequest | None = None,
) -> dict[str, Any]:
    try:
        focus = payload.focus_prompt if payload is not None else None
        return generate_briefing(user_id=current_user["id"], focus_prompt=focus)
    except BriefingAINotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BriefingGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/briefings/{briefing_id}/chat")
def briefings_chat(
    briefing_id: int,
    body: BriefingChatRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        reply = chat_with_briefing(
            briefing_id,
            body.message,
            [{"role": m.role, "content": m.content} for m in body.history],
            user_id=current_user["id"],
        )
    except BriefingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="briefing not found") from exc
    except BriefingAINotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"reply": reply}
