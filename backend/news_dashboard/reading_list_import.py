"""Import saved articles from third-party read-it-later services.

Supports Pocket (CSV or HTML export), Instapaper (CSV export), and Omnivore
(JSON export). Each imported item becomes an article (deduped by canonical
URL against anything already visible to the importing user), gets the
user's ``later`` workflow state, and has its tags (if any) applied. Article
bodies are never fetched during import — that happens lazily later via the
normal body-fetch/insights path, same as freshly ingested articles.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db, insert_article_sql
from news_dashboard.ingest import _find_canonical, canonicalize_url

logger = logging.getLogger(__name__)

SUPPORTED_SERVICES = frozenset({"pocket", "instapaper", "omnivore"})

# Keep imports fast and bounded; anything beyond this is dropped and reported
# via the `truncated` flag rather than processed in the background (there is
# no background job queue in this codebase to hand it off to).
MAX_IMPORT_ITEMS = 2000

_SERVICE_SOURCE_NAMES = {
    "pocket": "Pocket Import",
    "instapaper": "Instapaper Import",
    "omnivore": "Omnivore Import",
}


class ReadingListImportError(ValueError):
    """Raised when the uploaded export file can't be parsed at all."""


@dataclass
class ImportedItem:
    url: str
    title: str
    saved_at: str | None = None
    tags: list[str] = field(default_factory=list)


# ── Parsers ───────────────────────────────────────────────────────────────────


def _split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    seps = "|" if "|" in raw else ","
    return [t.strip() for t in raw.split(seps) if t.strip()]


def parse_pocket_csv(text: str) -> list[ImportedItem]:
    """Parse Pocket's CSV export (columns: title,url,time_added,tags,status)."""
    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        message = "Pocket CSV export has no header row"
        raise ReadingListImportError(message)
    fields = {(f or "").strip().lower(): f for f in reader.fieldnames}
    url_field = fields.get("url")
    if url_field is None:
        message = "Pocket CSV export is missing a 'url' column"
        raise ReadingListImportError(message)
    title_field = fields.get("title")
    time_field = fields.get("time_added")
    tags_field = fields.get("tags")

    items: list[ImportedItem] = []
    for row in reader:
        url = (row.get(url_field) or "").strip()
        if not url:
            continue
        title = (row.get(title_field, "") if title_field else "").strip() or url
        saved_at = None
        if time_field:
            raw_time = (row.get(time_field) or "").strip()
            if raw_time.isdigit():
                from datetime import datetime, timezone

                saved_at = (
                    datetime.fromtimestamp(int(raw_time), tz=timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                )
        tags = _split_tags(row.get(tags_field) if tags_field else None)
        items.append(ImportedItem(url=url, title=title, saved_at=saved_at, tags=tags))
    return items


class _PocketHtmlParser(HTMLParser):
    """Parse Pocket's legacy HTML export: `<li><a href=... tags="...">Title</a></li>`."""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[ImportedItem] = []
        self._in_anchor = False
        self._current: dict[str, Any] = {}
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_dict = dict(attrs)
        href = (attr_dict.get("href") or "").strip()
        if not href:
            return
        self._in_anchor = True
        self._text_parts = []
        from datetime import datetime, timezone

        saved_at = None
        time_added = attr_dict.get("time_added")
        if time_added and time_added.isdigit():
            saved_at = (
                datetime.fromtimestamp(int(time_added), tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat()
            )
        self._current = {
            "url": href,
            "saved_at": saved_at,
            "tags": _split_tags(attr_dict.get("tags")),
        }

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._in_anchor:
            return
        self._in_anchor = False
        title = "".join(self._text_parts).strip() or self._current["url"]
        self.items.append(
            ImportedItem(
                url=self._current["url"],
                title=title,
                saved_at=self._current["saved_at"],
                tags=self._current["tags"],
            )
        )


def parse_pocket_html(text: str) -> list[ImportedItem]:
    parser = _PocketHtmlParser()
    parser.feed(text)
    if not parser.items:
        message = "No links found in Pocket HTML export"
        raise ReadingListImportError(message)
    return parser.items


def parse_instapaper_csv(text: str) -> list[ImportedItem]:
    """Parse Instapaper's CSV export (columns: URL,Title,Selection,Folder)."""
    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        message = "Instapaper CSV export has no header row"
        raise ReadingListImportError(message)
    fields = {(f or "").strip().lower(): f for f in reader.fieldnames}
    url_field = fields.get("url")
    if url_field is None:
        message = "Instapaper CSV export is missing a 'URL' column"
        raise ReadingListImportError(message)
    title_field = fields.get("title")
    folder_field = fields.get("folder")

    items: list[ImportedItem] = []
    for row in reader:
        url = (row.get(url_field) or "").strip()
        if not url:
            continue
        title = (row.get(title_field, "") if title_field else "").strip() or url
        folder = (row.get(folder_field, "") if folder_field else "").strip()
        tags = [folder] if folder and folder.lower() not in ("unread", "archive") else []
        items.append(ImportedItem(url=url, title=title, tags=tags))
    return items


def parse_omnivore_json(text: str) -> list[ImportedItem]:
    """Parse an Omnivore export: a JSON array of `{url, title, savedAt, labels}` objects."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        message = f"Invalid Omnivore JSON export: {exc}"
        raise ReadingListImportError(message) from exc

    if isinstance(data, dict):
        data = data.get("articles") or data.get("items") or []
    if not isinstance(data, list):
        message = "Omnivore export must be a JSON array (or an object with an 'articles' list)"
        raise ReadingListImportError(message)

    items: list[ImportedItem] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or entry.get("originalArticleUrl") or "").strip()
        if not url:
            continue
        title = str(entry.get("title") or "").strip() or url
        saved_at = entry.get("savedAt") or entry.get("saved_at")
        labels = entry.get("labels") or []
        tags: list[str] = []
        for label in labels:
            if isinstance(label, dict):
                name = str(label.get("name") or "").strip()
            else:
                name = str(label or "").strip()
            if name:
                tags.append(name)
        items.append(
            ImportedItem(
                url=url,
                title=title,
                saved_at=str(saved_at) if saved_at else None,
                tags=tags,
            )
        )
    return items


def parse_export(service: str, filename: str, contents: bytes) -> list[ImportedItem]:
    if service not in SUPPORTED_SERVICES:
        message = f"unsupported service: {service!r} (expected one of {sorted(SUPPORTED_SERVICES)})"
        raise ReadingListImportError(message)

    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        message = f"Could not decode file as UTF-8: {exc}"
        raise ReadingListImportError(message) from exc

    if service == "pocket":
        stripped = text.lstrip()
        is_html = stripped.startswith("<") or filename.lower().endswith((".html", ".htm"))
        return parse_pocket_html(text) if is_html else parse_pocket_csv(text)
    if service == "instapaper":
        return parse_instapaper_csv(text)
    return parse_omnivore_json(text)


# ── Import orchestration ──────────────────────────────────────────────────────


def _ensure_import_source(conn: Any, user_id: int, service: str) -> str:
    """Return the slug of this user's private, disabled source for `service` imports.

    Disabled so scheduled ingestion never tries to fetch it as a feed; it exists
    only to give imported articles a `source_slug` and a private-visibility owner.
    """
    slug = f"import-{service}-{user_id}"
    name = _SERVICE_SOURCE_NAMES[service]
    url = f"urn:reading-list-import:{service}"
    conn.execute(
        """
        INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
        VALUES (%s, %s, %s, %s, %s, 0, FALSE, %s)
        ON CONFLICT (slug) DO NOTHING
        """,
        (slug, name, url, "imported", "reading_list_import", user_id),
    )
    return slug


def _get_or_create_tag_id(conn: Any, user_id: int, name: str, cache: dict[str, int]) -> int:
    if name in cache:
        return cache[name]
    row = conn.execute(
        """
        INSERT INTO user_tags (user_id, name)
        VALUES (%s, %s)
        ON CONFLICT (user_id, name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (user_id, name),
    ).fetchone()
    tag_id = int(row["id"] if isinstance(row, dict) else row[0])
    cache[name] = tag_id
    return tag_id


def import_reading_list(
    user_id: int,
    service: str,
    filename: str,
    contents: bytes,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Import a Pocket/Instapaper/Omnivore export for `user_id`.

    Returns a summary: `{"added": [...], "skipped": [...], "failed": [...],
    "truncated": bool}`. Safe to call repeatedly with the same file — already
    imported articles are matched by canonical URL and reported as skipped
    rather than duplicated.
    """
    items = parse_export(service, filename, contents)

    truncated = len(items) > MAX_IMPORT_ITEMS
    items = items[:MAX_IMPORT_ITEMS]

    init_db(db_path)
    added: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    tag_cache: dict[str, int] = {}

    with connect(db_path) as conn:
        source_slug = _ensure_import_source(conn, user_id, service)
        source_name = _SERVICE_SOURCE_NAMES[service]

        for item in items:
            url = item.url.strip()
            if not url.lower().startswith(("http://", "https://")):
                failed.append({"url": url, "error": "invalid or unsupported URL scheme"})
                continue

            try:
                with conn.transaction():
                    canonical = canonicalize_url(url)
                    existing_id = _find_canonical(
                        conn, canonical, item.title, owner_user_id=user_id
                    )
                    if existing_id is not None:
                        article_id = existing_id
                        is_new = False
                    else:
                        conn.execute(
                            insert_article_sql(),
                            (
                                url,
                                canonical,
                                item.title,
                                source_slug,
                                source_name,
                                "imported",
                                "reading_list_import",
                                item.saved_at,
                                "",
                                f"Imported from {source_name}.",
                                50,
                                ",".join(item.tags),
                                None,
                                None,
                                None,
                            ),
                        )
                        row = conn.execute(
                            "SELECT id FROM articles WHERE url = %s", (url,)
                        ).fetchone()
                        if row is None:
                            failed.append({"url": url, "error": "failed to import article"})
                            continue
                        article_id = int(row["id"] if isinstance(row, dict) else row[0])
                        is_new = True

                    # Only claim a workflow state if the user doesn't already have one for
                    # this article — re-importing shouldn't revert progress on articles
                    # already triaged (e.g. marked done) via normal ingestion.
                    conn.execute(
                        """
                        INSERT INTO user_article_state (user_id, article_id, state)
                        VALUES (%s, %s, 'later')
                        ON CONFLICT (user_id, article_id) DO NOTHING
                        """,
                        (user_id, article_id),
                    )

                    for tag_name in item.tags:
                        tag_id = _get_or_create_tag_id(conn, user_id, tag_name, tag_cache)
                        conn.execute(
                            """
                            INSERT INTO article_tags (user_id, article_id, tag_id)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (user_id, article_id, tag_id) DO NOTHING
                            """,
                            (user_id, article_id, tag_id),
                        )
            except Exception:
                logger.exception("Failed to import reading-list item: %s", url)
                failed.append({"url": url, "error": "failed to import article"})
                continue

            if is_new:
                added.append({"url": url, "title": item.title})
            else:
                skipped.append({"url": url, "reason": "duplicate"})

    return {"added": added, "skipped": skipped, "failed": failed, "truncated": truncated}
