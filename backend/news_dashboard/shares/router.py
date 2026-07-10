"""HTTP routes for the shares domain."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
)

from news_dashboard.auth import (
    require_auth,
)
from news_dashboard.body_fetch import get_article
from news_dashboard.shares.models import (
    AddAnnotationRequest,
    AddMessageRequest,
    ShareArticleRequest,
)

router = APIRouter()


def _notify_share_recipient(*, to_user_id: int, sender: str, article_title: str) -> None:
    from news_dashboard.push import send_push_for_user

    send_push_for_user(
        to_user_id,
        f"{sender} shared an article",
        article_title,
        target_url="/shared",
        tag="shared-article",
    )


def _generate_share_context_bg(*, share_id: int) -> None:
    from news_dashboard.shares.service import generate_share_context

    generate_share_context(share_id)


@router.get("/api/users")
def list_shareable_users(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import shareable_users

    return {"items": shareable_users(current_user["id"])}


@router.post("/api/articles/{article_id}/share")
def share_article_endpoint(
    article_id: int,
    payload: ShareArticleRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    from news_dashboard.shares.service import ShareError, share_article

    try:
        share = share_article(
            article_id=article_id,
            from_user_id=current_user["id"],
            to_user_id=payload.to_user_id,
            note=payload.note,
        )
    except ShareError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    article = get_article(article_id, user_id=current_user["id"])
    title = article["title"] if article else "an article"
    background_tasks.add_task(
        _notify_share_recipient,
        to_user_id=payload.to_user_id,
        sender=current_user["username"],
        article_title=title,
    )
    background_tasks.add_task(_generate_share_context_bg, share_id=int(share["id"]))
    return share


@router.get("/api/shares")
def list_shares(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import list_received_shares, unread_share_count

    return {
        "items": list_received_shares(current_user["id"]),
        "unread": unread_share_count(current_user["id"]),
    }


@router.get("/api/shares/sent")
def list_sent_shares_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import list_sent_shares

    return {"items": list_sent_shares(current_user["id"])}


@router.post("/api/shares/{share_id}/revoke")
def revoke_share_endpoint(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import revoke_share

    share = revoke_share(share_id, current_user["id"])
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return share


@router.get("/api/shares/unread_count")
def shares_unread_count(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import unread_share_count

    return {"unread": unread_share_count(current_user["id"])}


@router.post("/api/shares/{share_id}/read")
def mark_share_read_endpoint(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import mark_share_read

    return {"ok": mark_share_read(share_id, current_user["id"])}


@router.get("/api/shares/{share_id}")
def get_share_endpoint(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import get_share

    share = get_share(share_id, current_user["id"])
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return share


@router.get("/api/shares/{share_id}/article")
def get_shared_article_endpoint(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import get_shared_article

    article = get_shared_article(share_id, current_user["id"])
    if article is None:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@router.post("/api/shares/{share_id}/article/body")
def fetch_shared_article_body_endpoint(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import fetch_shared_article_body

    article = fetch_shared_article_body(share_id, current_user["id"])
    if article is None:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@router.get("/api/shares/{share_id}/annotations")
def list_share_annotations(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import get_share, list_annotations

    if get_share(share_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"items": list_annotations(share_id)}


@router.post("/api/shares/{share_id}/annotations")
def add_share_annotation(
    share_id: int,
    payload: AddAnnotationRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    from news_dashboard.shares.service import add_annotation, get_share

    if get_share(share_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="Share not found")
    annotation = add_annotation(
        share_id,
        highlighted_text=payload.highlighted_text,
        offset_chars=payload.offset_chars,
        note=payload.note,
    )
    background_tasks.add_task(_generate_share_context_bg, share_id=share_id)
    return annotation


@router.get("/api/shares/{share_id}/messages")
def list_share_messages(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import get_share, list_messages

    if get_share(share_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"items": list_messages(share_id)}


@router.post("/api/shares/{share_id}/messages")
def add_share_message(
    share_id: int,
    payload: AddMessageRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares.service import add_message, get_share

    if get_share(share_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return add_message(share_id, current_user["id"], payload.message)
