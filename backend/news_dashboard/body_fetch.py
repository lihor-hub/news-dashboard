"""Fetch and cache article body text on first reader open (issue #79).

Uses stdlib only (urllib + html.parser) — no extra dependencies.
Extracted text is stored in articles.body / articles.body_status.
Subsequent opens serve the cache; no bulk crawling at ingest.
"""

from __future__ import annotations

import logging
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .db import connect, init_db, row_to_dict
from .scraper import TIMEOUT_SECS, USER_AGENT

logger = logging.getLogger(__name__)

# Tags whose entire subtree we skip
_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "aside",
        "noscript",
        "iframe",
        "form",
        "button",
        "select",
        "option",
        "input",
        "textarea",
        "svg",
        "path",
        "figure",
    }
)

# Block-level tags that trigger a paragraph break
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "main",
        "blockquote",
        "li",
        "dt",
        "dd",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "pre",
        "br",
        "tr",
    }
)


class _BodyExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []
        self._current: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth or tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._current.append(text)

    def _flush(self) -> None:
        text = " ".join(self._current).strip()
        if text:
            self._chunks.append(text)
        self._current = []

    def result(self) -> str:
        self._flush()
        paragraphs: list[str] = []
        for raw_chunk in self._chunks:
            cleaned = re.sub(r"\s+", " ", raw_chunk).strip()
            if len(cleaned) > 40:
                paragraphs.append(cleaned)
        return "\n\n".join(paragraphs)


def extract_body(url: str) -> tuple[str, str]:
    """Fetch URL and extract readable text.

    Returns (body_text, 'ok') on success or ('', 'error') on failure.
    """
    if not url.startswith(("http:", "https:")):
        return "", "error"
    try:
        req = urllib.request.Request(  # noqa: S310 - scheme validated above
            url, headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:  # noqa: S310
            raw: bytes = resp.read(500_000)  # cap at ~500 KB
            charset = resp.headers.get_content_charset("utf-8") or "utf-8"
            html = raw.decode(str(charset), errors="replace")
    except Exception as exc:
        logger.warning("body_fetch: fetch failed for %r: %s", url, exc)
        return "", "error"

    try:
        parser = _BodyExtractor()
        parser.feed(html)
        text = parser.result()
    except Exception as exc:
        logger.warning("body_fetch: parse failed for %r: %s", url, exc)
        return "", "error"

    if not text.strip():
        return "", "error"

    return text, "ok"


def fetch_and_cache_body(article_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    """Fetch and store body for an article. Returns the updated article dict or None if not found.

    If body_status is already 'ok', returns the cached row immediately.
    """
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, url, body, body_status FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        if row is None:
            return None
        row_d = row_to_dict(row)
        if row_d.get("body_status") == "ok":
            full_row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            return row_to_dict(full_row) if full_row else None

    url = row_d["url"]
    body, status = extract_body(url)

    with connect(db_path) as conn:
        conn.execute(
            "UPDATE articles SET body = ?, body_status = ?,"
            " updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (body if status == "ok" else None, status, article_id),
        )
        full_row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if full_row is None:
            return None
        result = row_to_dict(full_row)
        # Strip internal columns
        result.pop("embedding", None)
        result.pop("fts_vector", None)
        return result


def get_article(article_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    """Fetch a single article by ID, stripping internal columns."""
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if row is None:
            return None
        d = row_to_dict(row)
        d.pop("embedding", None)
        d.pop("fts_vector", None)
        return d
