"""Reading list persistence and background metadata enrichment."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from news_dashboard.db import connect, init_db
from news_dashboard.reading_list.importers import ImportedItem
from news_dashboard.reading_list.metadata import detect_kind, fetch_url_metadata

logger = logging.getLogger(__name__)

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


class InvalidReadingListUrlError(ValueError):
    """Raised when a URL cannot be saved to the reading list."""


def _require_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        message = f"Not a fetchable http(s) URL: {url!r}"
        raise InvalidReadingListUrlError(message)


def normalize_url(url: str) -> str:
    """Canonicalize a URL for per-user deduplication.

    Lowercases scheme/host, drops fragments and common tracking parameters,
    and strips trailing slashes from the path.
    """
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(_TRACKING_PARAM_PREFIXES)
        and key.lower() not in _TRACKING_PARAMS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), host, path, "", urlencode(query), ""))


def _serialize(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("created_at", "fetched_at", "done_at"):
        value = item.get(key)
        if value is not None:
            item[key] = value.isoformat()
    return item


def add_item(
    user_id: int,
    url: str,
    note: str | None = None,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Save a URL for the user; returns the existing item on duplicate.

    The returned dict carries a ``created`` flag so callers can distinguish
    a fresh insert (which needs a metadata fetch) from a dedupe hit.
    """
    cleaned = url.strip()
    _require_http_url(cleaned)
    normalized = normalize_url(cleaned)
    kind = detect_kind(cleaned)
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO reading_list_items(user_id, url, normalized_url, kind, note, priority)
            VALUES (
              %s, %s, %s, %s, %s,
              (SELECT COALESCE(MAX(priority), 0) + 1 FROM reading_list_items WHERE user_id = %s)
            )
            ON CONFLICT (user_id, normalized_url) DO NOTHING
            RETURNING *
            """,
            (user_id, cleaned, normalized, kind, note, user_id),
        ).fetchone()
        if row is not None:
            return _serialize(row) | {"created": True}
        existing = conn.execute(
            "SELECT * FROM reading_list_items WHERE user_id = %s AND normalized_url = %s",
            (user_id, normalized),
        ).fetchone()
    return _serialize(existing) | {"created": False}


def list_items(
    user_id: int,
    status: str | None = None,
    *,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(database_url=database_url)
    query = "SELECT * FROM reading_list_items WHERE user_id = %s"
    params: list[Any] = [user_id]
    if status is not None:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY priority ASC, created_at ASC, id ASC"
    with connect(database_url=database_url) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_serialize(row) for row in rows]


def update_item(
    user_id: int,
    item_id: int,
    *,
    status: str | None = None,
    note: str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE reading_list_items
            SET status = COALESCE(%s, status),
                note = COALESCE(%s, note),
                done_at = CASE
                  WHEN %s::text = 'done' THEN NOW()
                  WHEN %s::text IS NOT NULL THEN NULL
                  ELSE done_at
                END
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (status, note, status, status, item_id, user_id),
        ).fetchone()
    return _serialize(row) if row is not None else None


def reorder_items(
    user_id: int,
    ordered_ids: list[int],
    *,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    """Persist an explicit priority order for the user's items."""
    with connect(database_url=database_url) as conn:
        for position, item_id in enumerate(ordered_ids, start=1):
            conn.execute(
                "UPDATE reading_list_items SET priority = %s WHERE id = %s AND user_id = %s",
                (position, item_id, user_id),
            )
    return list_items(user_id, database_url=database_url)


def delete_item(
    user_id: int,
    item_id: int,
    *,
    database_url: str | None = None,
) -> bool:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "DELETE FROM reading_list_items WHERE id = %s AND user_id = %s RETURNING id",
            (item_id, user_id),
        ).fetchone()
    return row is not None


def fetch_metadata_for_item(item_id: int, *, database_url: str | None = None) -> None:
    """Fetch and store preview metadata for one item.

    Failures are recorded on the row (``fetch_status='error'``) instead of
    raised, so background callers never crash the sweep.
    """
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "SELECT url FROM reading_list_items WHERE id = %s",
            (item_id,),
        ).fetchone()
    if row is None:
        return
    try:
        meta = fetch_url_metadata(row["url"])
    except Exception as exc:
        logger.warning("Reading list metadata fetch failed for %s: %s", row["url"], exc)
        with connect(database_url=database_url) as conn:
            conn.execute(
                """
                UPDATE reading_list_items
                SET fetch_status = 'error', fetch_error = %s, fetched_at = NOW()
                WHERE id = %s
                """,
                (str(exc)[:500], item_id),
            )
        return
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            UPDATE reading_list_items
            SET title = %s,
                description = %s,
                image_url = %s,
                site_name = %s,
                kind = COALESCE(%s, kind),
                fetch_status = 'ok',
                fetch_error = NULL,
                fetched_at = NOW()
            WHERE id = %s
            """,
            (
                meta.get("title"),
                meta.get("description"),
                meta.get("image_url"),
                meta.get("site_name"),
                meta.get("kind"),
                item_id,
            ),
        )


def process_pending_items(*, limit: int = 20, database_url: str | None = None) -> int:
    """Fetch metadata for items still pending; returns the number processed."""
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT id FROM reading_list_items
            WHERE fetch_status = 'pending'
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    for row in rows:
        fetch_metadata_for_item(row["id"], database_url=database_url)
    return len(rows)


class ImportTooLargeError(ValueError):
    """Raised when an import file has more items than the batch cap allows."""


def import_items(
    user_id: int,
    items: list[ImportedItem],
    *,
    max_items: int,
    database_url: str | None = None,
) -> dict[str, int]:
    """Bulk-insert reading list items from a third-party export.

    Titles carried over from the export are trusted as-is (fetch_status is
    marked ``ok`` so the background sweep never overwrites them); items
    without a title are left ``pending`` for the usual metadata fetch.
    Duplicates (by normalized URL, per user) are skipped rather than
    failed. Tags have no home on reading list items yet, so they are
    folded into the item's note as a readable summary.
    """
    if len(items) > max_items:
        message = f"Import contains {len(items)} items; the limit is {max_items}"
        raise ImportTooLargeError(message)

    init_db(database_url=database_url)
    added = 0
    skipped = 0
    failed = 0
    with connect(database_url=database_url) as conn:
        for item in items:
            try:
                _require_http_url(item.url)
            except InvalidReadingListUrlError:
                failed += 1
                continue
            normalized = normalize_url(item.url)
            kind = detect_kind(item.url)
            note = f"Tags: {', '.join(item.tags)}" if item.tags else None
            fetch_status = "ok" if item.title else "pending"
            row = conn.execute(
                """
                INSERT INTO reading_list_items(
                    user_id, url, normalized_url, title, kind, fetch_status,
                    status, note, priority, created_at, done_at
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s,
                  (SELECT COALESCE(MAX(priority), 0) + 1
                     FROM reading_list_items WHERE user_id = %s),
                  COALESCE(%s, NOW()),
                  CASE WHEN %s = 'archived' THEN COALESCE(%s, NOW()) END
                )
                ON CONFLICT (user_id, normalized_url) DO NOTHING
                RETURNING id
                """,
                (
                    user_id,
                    item.url,
                    normalized,
                    item.title,
                    kind,
                    fetch_status,
                    item.status,
                    note,
                    user_id,
                    item.created_at,
                    item.status,
                    item.created_at,
                ),
            ).fetchone()
            if row is not None:
                added += 1
            else:
                skipped += 1
    return {"added": added, "skipped": skipped, "failed": failed}
