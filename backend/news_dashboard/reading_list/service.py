"""Reading list persistence and background metadata enrichment."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from news_dashboard.db import connect, init_db
from news_dashboard.reading_list.importers import ImportedItem
from news_dashboard.reading_list.metadata import detect_kind, fetch_url_metadata

logger = logging.getLogger(__name__)

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}

DEFAULT_SUMMARY_MODEL = "gpt-4o-mini"
_SUMMARY_PROMPT = (
    "You are helping a reader triage their reading list. Based ONLY on the title and "
    "description below, write one concise sentence (max 40 words) describing what this "
    "item is about, so the reader can decide whether to open it without reading further. "
    "Do not invent details that are not present in the text. Return only the sentence."
)


class ReadingListSummaryNotConfiguredError(Exception):
    """Raised when no AI chat credentials are configured for summary generation."""


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
    q: str | None = None,
    kind: str | None = None,
    *,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(database_url=database_url)
    query = "SELECT * FROM reading_list_items WHERE user_id = %s"
    params: list[Any] = [user_id]
    if status is not None:
        query += " AND status = %s"
        params.append(status)
    if kind is not None:
        query += " AND kind = %s"
        params.append(kind)
    if q is not None and q.strip():
        query += """
            AND (
                title ILIKE %s
                OR url ILIKE %s
                OR description ILIKE %s
                OR site_name ILIKE %s
                OR note ILIKE %s
            )
        """
        term = f"%{q.strip()}%"
        params.extend([term, term, term, term, term])
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
    generate_summary_for_item(item_id, database_url=database_url)


def _summary_ai_config() -> tuple[str, str | None, str]:
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        message = "FREE_LLM_API_KEY (or OPENAI_API_KEY) is not configured"
        raise ReadingListSummaryNotConfiguredError(message)
    model = os.getenv("OPENAI_READING_LIST_SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL)
    return api_key, base_url, model


def _call_summary_model(api_key: str, base_url: str | None, model: str, text: str) -> str:
    from news_dashboard.ai_client import chat_create, get_chat_client, get_prompt

    client = get_chat_client(api_key=api_key, base_url=base_url)
    prompt = get_prompt(
        "reading-list-summary",
        label="production",
        prompt_type="text",
        fallback=f"{_SUMMARY_PROMPT}\n\n{{{{reading_list_text}}}}",
        variables={"reading_list_text": text},
    )
    result = chat_create(
        client,
        name="reading-list-summary",
        tags=["reading-list"],
        prompt=prompt,
        model=model,
        messages=[{"role": "user", "content": prompt.text}],
        max_tokens=120,
    )
    summary = (result.choices[0].message.content or "").strip()
    if not summary:
        message = "empty summary response"
        raise ValueError(message)
    return summary


def generate_summary_for_item(item_id: int, *, database_url: str | None = None) -> None:
    """Generate and store an AI summary from an item's title/description.

    Failures are recorded on the row (``summary_status='error'``) instead of
    raised, so callers chaining this onto the metadata fetch never crash.
    Items with neither a title nor a description, or with AI credentials
    unconfigured, are marked ``summary_status='skipped'``.
    """
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "SELECT title, description FROM reading_list_items WHERE id = %s",
            (item_id,),
        ).fetchone()
    if row is None:
        return
    title = (row["title"] or "").strip()
    description = (row["description"] or "").strip()
    if not title and not description:
        with connect(database_url=database_url) as conn:
            conn.execute(
                "UPDATE reading_list_items SET summary_status = 'skipped' WHERE id = %s",
                (item_id,),
            )
        return
    text = f"Title: {title}\nDescription: {description}" if title else description

    try:
        api_key, base_url, model = _summary_ai_config()
    except ReadingListSummaryNotConfiguredError:
        logger.info("Reading list summary skipped for item %s: AI not configured", item_id)
        with connect(database_url=database_url) as conn:
            conn.execute(
                "UPDATE reading_list_items SET summary_status = 'skipped' WHERE id = %s",
                (item_id,),
            )
        return

    try:
        summary = _call_summary_model(api_key, base_url, model, text)
    except Exception as exc:
        logger.warning("Reading list summary generation failed for item %s: %s", item_id, exc)
        with connect(database_url=database_url) as conn:
            conn.execute(
                "UPDATE reading_list_items SET summary_status = 'error' WHERE id = %s",
                (item_id,),
            )
        return

    with connect(database_url=database_url) as conn:
        conn.execute(
            "UPDATE reading_list_items SET summary = %s, summary_status = 'ok' WHERE id = %s",
            (summary, item_id),
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
