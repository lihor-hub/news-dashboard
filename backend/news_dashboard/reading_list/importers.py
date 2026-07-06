"""Parsers for third-party read-it-later export formats.

Supports Pocket (CSV), Instapaper (CSV), and Omnivore (JSON) exports so
users migrating from those services can bring their saved articles into
the reading list. Each parser normalizes rows into a single
:class:`ImportedItem` shape the import endpoint can insert uniformly.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime


class ImportParseError(ValueError):
    """Raised when a file cannot be parsed as the requested export format."""


@dataclass
class ImportedItem:
    url: str
    title: str | None = None
    created_at: datetime | None = None
    tags: list[str] = field(default_factory=list)
    status: str = "unread"


def _parse_epoch(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        return datetime.fromtimestamp(int(value.strip()), tz=UTC)
    except (ValueError, OSError):
        return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _split_tags(value: str | None) -> list[str]:
    if not value or not value.strip():
        return []
    return [tag.strip() for tag in value.split(",") if tag.strip()]


def _decode(contents: bytes) -> str:
    try:
        return contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        message = "File is not valid UTF-8 text"
        raise ImportParseError(message) from exc


def parse_pocket_csv(contents: bytes) -> list[ImportedItem]:
    """Parse a Pocket CSV export: title,url,time_added,tags,status."""
    text = _decode(contents)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "url" not in {f.lower() for f in reader.fieldnames}:
        message = "Pocket export must be a CSV with a 'url' column"
        raise ImportParseError(message)
    lower_fields = {f.lower(): f for f in reader.fieldnames}
    items: list[ImportedItem] = []
    for row in reader:
        url = (row.get(lower_fields["url"]) or "").strip()
        if not url:
            continue
        raw_status = (row.get(lower_fields.get("status", ""), "") or "").strip().lower()
        items.append(
            ImportedItem(
                url=url,
                title=(row.get(lower_fields.get("title", "")) or "").strip() or None,
                created_at=_parse_epoch(row.get(lower_fields.get("time_added", ""))),
                tags=_split_tags(row.get(lower_fields.get("tags", ""))),
                status="archived" if raw_status == "archive" else "unread",
            )
        )
    return items


def parse_instapaper_csv(contents: bytes) -> list[ImportedItem]:
    """Parse an Instapaper CSV export: URL,Title,Selection,Folder,Timestamp."""
    text = _decode(contents)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "url" not in {f.lower() for f in reader.fieldnames}:
        message = "Instapaper export must be a CSV with a 'URL' column"
        raise ImportParseError(message)
    lower_fields = {f.lower(): f for f in reader.fieldnames}
    items: list[ImportedItem] = []
    for row in reader:
        url = (row.get(lower_fields["url"]) or "").strip()
        if not url:
            continue
        folder = (row.get(lower_fields.get("folder", ""), "") or "").strip().lower()
        timestamp_key = lower_fields.get("timestamp")
        items.append(
            ImportedItem(
                url=url,
                title=(row.get(lower_fields.get("title", "")) or "").strip() or None,
                created_at=_parse_epoch(row.get(timestamp_key)) if timestamp_key else None,
                tags=[],
                status="archived" if folder in {"archive", "archived"} else "unread",
            )
        )
    return items


def parse_omnivore_json(contents: bytes) -> list[ImportedItem]:
    """Parse an Omnivore JSON export: a list of {url, title, labels, savedAt, state}."""
    text = _decode(contents)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        message = "Omnivore export must be valid JSON"
        raise ImportParseError(message) from exc
    if isinstance(data, dict):
        found = data.get("items", data.get("articles"))
        if not isinstance(found, list):
            message = "Omnivore export must be a JSON array, or an object with an 'items' array"
            raise ImportParseError(message)
        data = found
    if not isinstance(data, list):
        message = "Omnivore export must be a JSON array of items"
        raise ImportParseError(message)
    items: list[ImportedItem] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or entry.get("originalArticleUrl") or "").strip()
        if not url:
            continue
        raw_labels = entry.get("labels") or []
        tags = [
            str(label.get("name")).strip() if isinstance(label, dict) else str(label).strip()
            for label in raw_labels
        ]
        state = str(entry.get("state") or "").strip().upper()
        title = entry.get("title")
        items.append(
            ImportedItem(
                url=url,
                title=str(title).strip() if title else None,
                created_at=_parse_iso(entry.get("savedAt")),
                tags=[tag for tag in tags if tag],
                status="archived" if state == "ARCHIVED" else "unread",
            )
        )
    return items


PARSERS = {
    "pocket": parse_pocket_csv,
    "instapaper": parse_instapaper_csv,
    "omnivore": parse_omnivore_json,
}

MAX_IMPORT_ITEMS = 5000

# Upload memory/parse protection, independent of MAX_IMPORT_ITEMS (which caps
# the database write size). 10 MiB comfortably covers 5,000 URL rows with
# titles and tags in any of the supported formats.
MAX_IMPORT_BYTES = 10 * 1024 * 1024
