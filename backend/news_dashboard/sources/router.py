"""HTTP routes for the sources domain."""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from typing import Annotated, Any

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_fromstring
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
)

from news_dashboard.auth import (
    require_auth,
)
from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.ingest.service import (
    FeedFetchError,
    clean_html,
    preview_source_entries,
)
from news_dashboard.source_health import (
    generate_subscription_cleanup_suggestions,
    list_source_health,
)
from news_dashboard.sources.models import (
    CreateSourceRequest,
    EnabledUpdate,
    HighPriorityUpdate,
    PreviewSourceRequest,
    SourceCleanupRequest,
    SubstackPreviewRequest,
)
from news_dashboard.sources.service import (
    SourceDefinition,
    SubstackUrlError,
    add_user_source_preference,
    list_sources_for_user,
    normalize_substack_feed_url,
    set_user_source_priority,
)
from news_dashboard.url_safety import UnsafeUrlError, validate_server_fetch_url

router = APIRouter()
logger = logging.getLogger(__name__)


MAX_OPML_IMPORT_BYTES = int(os.getenv("MAX_OPML_IMPORT_BYTES", str(5 * 1024 * 1024)))


MAX_OPML_IMPORT_OUTLINES = int(os.getenv("MAX_OPML_IMPORT_OUTLINES", "1000"))
_PREVIEW_MAX_ITEMS = 5


def _private_source_slug(owner_user_id: int, slug: str) -> str:
    """Namespace a requested slug to the owning user's private source rows.

    ``sources.slug`` is a global primary key, so two users requesting the same
    human-friendly slug (e.g. "my-blog") would otherwise collide with a 409 even
    though each source is private to its owner. Namespacing the stored slug by
    owner keeps the requested name available to every user while the primary
    key stays globally unique.
    """
    return f"u{owner_user_id}-{slug}"[:120]


def _generate_opml(sources: list[dict[str, Any]]) -> str:
    """Generate an OPML 2.0 XML document from a list of source dicts."""
    opml = ET.Element("opml", version="2.0")
    head = ET.SubElement(opml, "head")
    title_el = ET.SubElement(head, "title")
    title_el.text = "News Dashboard Subscriptions"
    body = ET.SubElement(opml, "body")
    for src in sources:
        outline = ET.SubElement(body, "outline")
        outline.set("type", "rss")
        outline.set("text", src.get("name", ""))
        outline.set("title", src.get("name", ""))
        outline.set("xmlUrl", src.get("url", ""))
        html_url = src.get("html_url") or src.get("site_url")
        if html_url:
            outline.set("htmlUrl", html_url)
    return ET.tostring(opml, encoding="unicode", xml_declaration=True)


@router.get("/api/sources")
def sources(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    items = list_sources_for_user(int(current_user["id"]))
    return {"items": items}


@router.post("/api/sources")
def create_source(
    payload: CreateSourceRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Create a private custom source owned by the current user."""
    uid = current_user["id"]

    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name must not be empty")

    payload.validate_kind()

    try:
        validate_server_fetch_url(payload.url)
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    requested_slug = payload.validated_slug(payload.name)
    slug = _private_source_slug(uid, requested_slug)

    init_db()
    with connect() as conn:
        if payload.provider == "substack":
            existing = conn.execute(
                """
                SELECT slug, url
                FROM sources
                WHERE deleted_at IS NULL
                  AND (
                    slug = %s
                    OR (url = %s AND (owner_user_id IS NULL OR owner_user_id = %s))
                  )
                """,
                (slug, payload.url, uid),
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT slug, url FROM sources WHERE slug = %s",
                (slug,),
            ).fetchone()
        if existing:
            if existing["slug"] == slug:
                raise HTTPException(
                    status_code=409, detail=f"source slug '{requested_slug}' already exists"
                )
            raise HTTPException(
                status_code=409,
                detail="This feed is already in your sources.",
            )
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
            VALUES (%s, %s, %s, %s, %s, 0, TRUE, %s)
            """,
            (slug, payload.name.strip(), payload.url, payload.category, payload.kind, uid),
        )
        add_user_source_preference(
            conn,
            user_id=int(uid),
            source_slug=slug,
            high_priority=payload.high_priority,
        )
        row = conn.execute("SELECT * FROM sources WHERE slug = %s", (slug,)).fetchone()
    return {**row_to_dict(row), "subscribed": True, "high_priority": payload.high_priority}


@router.post("/api/sources/preview")
def preview_source(
    payload: PreviewSourceRequest,
    _current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Fetch a candidate source without persisting a source or article rows."""
    payload.validate_kind()

    try:
        validate_server_fetch_url(payload.url)
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source = SourceDefinition(
        slug="preview", name="preview", url=payload.url, category="preview", kind=payload.kind
    )
    try:
        entries = preview_source_entries(source)
    except FeedFetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    items = [
        {
            "title": clean_html(entry.get("title") or "Untitled")[:200],
            "url": entry.get("url", ""),
            "date": entry.get("date"),
        }
        for entry in entries[:_PREVIEW_MAX_ITEMS]
    ]
    return {
        "kind": payload.kind,
        "entry_count": len(entries),
        "items": items,
    }


@router.post("/api/sources/substack/preview")
def preview_substack_source(
    payload: SubstackPreviewRequest,
    _current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Normalize and preview a Substack publication without saving it."""
    try:
        substack_feed = normalize_substack_feed_url(payload.url)
        validate_server_fetch_url(substack_feed.feed_url)
    except (SubstackUrlError, UnsafeUrlError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source = SourceDefinition(
        slug="preview-substack",
        name=substack_feed.suggested_name,
        url=substack_feed.feed_url,
        category="newsletter",
        kind="rss_feed",
    )
    try:
        entries = preview_source_entries(source)
    except FeedFetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "feed_url": substack_feed.feed_url,
        "suggested_name": substack_feed.suggested_name,
        "entry_count": len(entries),
        "items": [
            {
                "title": clean_html(entry.get("title") or "Untitled")[:200],
                "url": entry.get("url", ""),
                "date": entry.get("date"),
            }
            for entry in entries[:_PREVIEW_MAX_ITEMS]
        ],
    }


@router.delete("/api/sources/{slug}")
def delete_source(
    slug: str,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Delete a private source. Only the owner can delete their own sources."""
    uid = current_user["id"]
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM sources WHERE slug = %s", (slug,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="source not found")
        src = row_to_dict(row)
        if src.get("owner_user_id") != uid:
            raise HTTPException(status_code=403, detail="cannot delete a source you don't own")
        if src.get("deleted_at") is not None:
            raise HTTPException(status_code=404, detail="source not found")
        conn.execute(
            "UPDATE sources SET deleted_at = NOW(), enabled = FALSE "
            "WHERE slug = %s AND owner_user_id = %s",
            (slug, uid),
        )
    return {"status": "deleted"}


@router.get("/api/sources/health")
def sources_health(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": list_source_health(user_id=int(current_user["id"]))}


@router.get("/api/sources/cleanup-suggestions")
def source_cleanup_suggestions(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": generate_subscription_cleanup_suggestions(int(current_user["id"]))}


@router.post("/api/sources/cleanup")
def source_cleanup(
    payload: SourceCleanupRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    uid = int(current_user["id"])
    requested_slugs = list(dict.fromkeys(payload.source_slugs))
    if not requested_slugs:
        return {"updated": [], "skipped": []}

    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT slug, owner_user_id
            FROM sources
            WHERE slug = ANY(%s)
              AND (owner_user_id IS NULL OR owner_user_id = %s)
              AND deleted_at IS NULL
            """,
            (requested_slugs, uid),
        ).fetchall()
        allowed = {str(row["slug"]): row_to_dict(row) for row in rows}
        updated: list[str] = []
        for slug in requested_slugs:
            source = allowed.get(slug)
            if source is None:
                continue
            if source.get("owner_user_id") is None:
                conn.execute(
                    """
                    INSERT INTO user_sources(user_id, source_slug, enabled)
                    VALUES (%s, %s, FALSE)
                    ON CONFLICT(user_id, source_slug)
                    DO UPDATE SET enabled = excluded.enabled
                    """,
                    (uid, slug),
                )
            else:
                conn.execute(
                    "UPDATE sources SET enabled = FALSE WHERE slug = %s AND owner_user_id = %s",
                    (slug, uid),
                )
            updated.append(slug)

    return {
        "updated": updated,
        "skipped": [slug for slug in requested_slugs if slug not in updated],
    }


@router.get("/api/sources/export.opml")
def export_opml(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> Response:
    """Export the user's enabled RSS-type sources as an OPML 2.0 document."""
    init_db()
    uid = current_user["id"]
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT s.*,
              CASE WHEN s.owner_user_id IS NULL THEN COALESCE(us.enabled, true)
                   ELSE (s.enabled IS TRUE) END AS user_enabled
            FROM sources s
            LEFT JOIN user_sources us ON us.source_slug = s.slug AND us.user_id = %s
            WHERE (s.owner_user_id IS NULL OR s.owner_user_id = %s)
              AND s.deleted_at IS NULL
              AND s.kind = %s
              AND (CASE WHEN s.owner_user_id IS NULL THEN COALESCE(us.enabled, true)
                   ELSE (s.enabled IS TRUE) END) = %s
            ORDER BY s.category, s.priority DESC, s.name
            """,
            (uid, uid, "rss_feed", True),
        ).fetchall()
        items = []
        for row in rows:
            d = row_to_dict(row)
            d["subscribed"] = bool(d.pop("user_enabled", 1))
            items.append(d)
    opml_xml = _generate_opml(items)
    return Response(
        content=opml_xml,
        media_type="text/x-opml",
        headers={
            "Content-Disposition": 'attachment; filename="subscriptions.opml"',
        },
    )


@router.post("/api/sources/import")
def import_opml(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """Import RSS feed subscriptions from an OPML file."""
    init_db()
    uid = current_user["id"]
    contents = file.file.read(MAX_OPML_IMPORT_BYTES + 1)
    if len(contents) > MAX_OPML_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"OPML file too large (max {MAX_OPML_IMPORT_BYTES} bytes); "
                "split it into smaller files and import them separately"
            ),
        )
    try:
        root = safe_fromstring(contents)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid OPML: {exc}") from exc

    outlines = root.findall(".//outline")
    if len(outlines) > MAX_OPML_IMPORT_OUTLINES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"OPML file has too many outlines ({len(outlines)}, "
                f"max {MAX_OPML_IMPORT_OUTLINES}); split it into smaller files"
            ),
        )
    added: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    with connect() as conn:
        for outline in outlines:
            xml_url = outline.get("xmlUrl")
            if not xml_url or not xml_url.strip():
                continue
            xml_url = xml_url.strip()

            # Validate the URL using the same safety check as create_source
            try:
                validate_server_fetch_url(xml_url)
            except UnsafeUrlError as exc:
                logger.warning(
                    "Rejected unsafe OPML source URL during import: %s", xml_url, exc_info=exc
                )
                failed.append({"url": xml_url, "error": "invalid or unsafe feed URL"})
                continue

            name = outline.get("text") or outline.get("title") or xml_url
            if not name.strip():
                name = xml_url
            name = name.strip()
            category = outline.get("category") or "tech"

            # Generate slug using the same logic as CreateSourceRequest
            payload = CreateSourceRequest(
                url=xml_url, name=name, category=category, kind="rss_feed"
            )
            try:
                slug = _private_source_slug(uid, payload.validated_slug(name))
            except HTTPException:
                failed.append({"url": xml_url, "error": "could not derive a valid slug"})
                continue

            # Skip duplicates: the namespaced slug is only reused if this same user already
            # imported it, so it never collides with another user's private source. For the
            # URL, only match sources already visible to this user (their own, or a global
            # default) — a different user's private source sharing the same URL is not a
            # duplicate for this user.
            existing = conn.execute(
                """
                SELECT 1 FROM sources
                WHERE slug = %s
                   OR (url = %s AND (owner_user_id IS NULL OR owner_user_id = %s))
                """,
                (slug, xml_url, uid),
            ).fetchone()
            if existing:
                skipped.append({"url": xml_url, "reason": "duplicate"})
                continue

            try:
                # A savepoint keeps a constraint violation here (e.g. a slug that slipped
                # past the duplicate check via a race) from aborting the whole request's
                # transaction and breaking the remaining outlines in this loop.
                with conn.transaction():
                    conn.execute(
                        """
                        INSERT INTO sources(
                            slug, name, url, category, kind, priority, enabled, owner_user_id
                        )
                        VALUES (%s, %s, %s, %s, %s, 0, TRUE, %s)
                        """,
                        (slug, name, xml_url, category, "rss_feed", uid),
                    )
                row = conn.execute("SELECT * FROM sources WHERE slug = %s", (slug,)).fetchone()
                added.append(row_to_dict(row))
            except Exception:
                logger.exception("Failed to import OPML source URL: %s", xml_url)
                failed.append({"url": xml_url, "error": "failed to import source"})

    return {"added": added, "skipped": skipped, "failed": failed}


@router.patch("/api/sources/{slug}/enabled")
def set_source_enabled(
    slug: str,
    payload: EnabledUpdate,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """For global sources: set per-user subscription. For private sources: set enabled flag."""
    uid = current_user["id"]
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM sources WHERE slug = %s", (slug,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="source not found")
        src = row_to_dict(row)
        if src.get("deleted_at") is not None:
            raise HTTPException(status_code=404, detail="source not found")
        if src.get("owner_user_id") is None:
            # Global source — write to user_sources subscription table
            conn.execute(
                """
                INSERT INTO user_sources(user_id, source_slug, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = excluded.enabled
                """,
                (uid, slug, bool(payload.enabled)),
            )
        else:
            # Private source — only owner can change
            if src.get("owner_user_id") != uid:
                raise HTTPException(status_code=403, detail="cannot modify a source you don't own")
            conn.execute(
                "UPDATE sources SET enabled = %s WHERE slug = %s",
                (bool(payload.enabled), slug),
            )
        row = conn.execute("SELECT * FROM sources WHERE slug = %s", (slug,)).fetchone()
    return {**row_to_dict(row), "subscribed": payload.enabled}


@router.patch("/api/sources/{slug}/priority")
def set_source_priority(
    slug: str,
    payload: HighPriorityUpdate,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Set the current user's attention priority for a visible source."""
    uid = int(current_user["id"])
    source = set_user_source_priority(
        user_id=uid,
        source_slug=slug,
        high_priority=payload.high_priority,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    return source
