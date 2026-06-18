"""Fetch and cache article body text on first reader open (issue #79).

Uses stdlib only (urllib + html.parser) — no extra dependencies.
Extracted text is stored in articles.body / articles.body_status.
Subsequent opens serve the cache; no bulk crawling at ingest.
"""

from __future__ import annotations

import logging
import os
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .db import connect, init_db, row_to_dict
from .scraper import TIMEOUT_SECS, USER_AGENT

logger = logging.getLogger(__name__)

_AI_HTML_LIMIT = 15_000
_AI_MODEL = "gpt-4o-mini"
_AI_PROMPT = (
    "Extract the main article text from this HTML. "
    "Return only the article body as plain text, no HTML tags."
)


def _ai_extract_body(url: str) -> tuple[str, str]:
    """Fallback: fetch raw HTML via httpx and extract body text via OpenAI.

    Returns (text, 'ok') on success or ('', 'error') if OPENAI_API_KEY is
    absent, the HTTP fetch fails, or the AI call fails.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "", "error"

    try:
        import httpx  # lazy import — optional at module load time

        resp = httpx.get(
            url,
            timeout=15,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        html = resp.text[:_AI_HTML_LIMIT]
    except Exception as exc:
        logger.warning("ai_body_fetch: HTTP fetch failed for %r: %s", url, exc)
        return "", "error"

    try:
        from openai import OpenAI  # lazy import — optional dep at import time

        client = OpenAI(api_key=api_key)
        result = client.chat.completions.create(
            model=_AI_MODEL,
            messages=[{"role": "user", "content": f"{_AI_PROMPT}\n\n{html}"}],
            max_tokens=2048,
        )
        text = (result.choices[0].message.content or "").strip()
        if not text:
            return "", "error"
        logger.info("ai_body_fetch: AI extraction succeeded for %r", url)
        return text, "ok"
    except Exception as exc:
        logger.warning("ai_body_fetch: AI extraction failed for %r: %s", url, exc)
        return "", "error"


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

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
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


def _merge_user_state(
    d: dict[str, Any], conn: Any, article_id: int, user_id: int
) -> dict[str, Any]:
    """Overlay per-user state from user_article_state onto an article dict in-place."""
    uas_row = conn.execute(
        "SELECT * FROM user_article_state WHERE user_id = %s AND article_id = %s",
        (user_id, article_id),
    ).fetchone()
    uas = row_to_dict(uas_row) if uas_row else None
    if uas is None:
        d["state"] = "today"
        d["starred"] = False
        for col in (
            "done_at",
            "starred_at",
            "skipped_at",
            "archived_at",
            "later_until",
            "restored_at",
        ):
            d[col] = None
    else:
        d["state"] = uas.get("state") or "today"
        d["starred"] = bool(uas.get("starred", False))
        d["done_at"] = uas.get("done_at")
        d["starred_at"] = uas.get("starred_at")
        d["skipped_at"] = uas.get("skipped_at")
        d["archived_at"] = uas.get("archived_at")
        d["later_until"] = uas.get("later_until")
        d["restored_at"] = uas.get("restored_at")
    return d


def _article_from_row(row: Any, conn: Any, article_id: int, user_id: int | None) -> dict[str, Any]:
    d = row_to_dict(row)
    d.pop("embedding", None)
    d.pop("fts_vector", None)
    if user_id is not None:
        _merge_user_state(d, conn, article_id, user_id)
    return d


def get_article(
    article_id: int,
    db_path: Path | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Fetch a single article by ID, stripping internal columns.

    When user_id is given the per-user state from user_article_state is merged
    in so that state/starred/timestamps reflect the calling user, not the
    global articles table defaults.
    """
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = %s", (article_id,)).fetchone()
        if row is None:
            return None
        return _article_from_row(row, conn, article_id, user_id)


def fetch_and_cache_body(
    article_id: int,
    db_path: Path | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Fetch and store body for an article. Returns the updated article dict or None if not found.

    If body_status is already 'ok', returns the cached row immediately.
    When user_id is given the returned dict reflects per-user state.
    """
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = %s", (article_id,)).fetchone()
        if row is None:
            return None
        row_d = row_to_dict(row)
        if row_d.get("body_status") == "ok":
            return _article_from_row(row, conn, article_id, user_id)

    url = row_d["url"]
    body, status = extract_body(url)
    if status == "error":
        body, status = _ai_extract_body(url)

    with connect(db_path) as conn:
        conn.execute(
            "UPDATE articles SET body = %s, body_status = %s,"
            " updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (body if status == "ok" else None, status, article_id),
        )

    return get_article(article_id, db_path=db_path, user_id=user_id)


def prefetch_article_bodies(limit: int = 20, db_path: Path | None = None) -> int:
    """Fetch and cache bodies for recently ingested articles that are still missing a body.

    Called as a background task after each ingest run to warm the body cache
    before users open those articles. Returns the count of articles that were
    successfully fetched.
    """
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM articles WHERE body_status = 'missing'"
            " ORDER BY discovered_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    ids = [int(row_to_dict(r)["id"]) for r in rows]
    if not ids:
        return 0
    logger.info("Body prefetch: warming cache for %d articles", len(ids))
    fetched = 0
    for article_id in ids:
        try:
            result = fetch_and_cache_body(article_id, db_path=db_path)
            if result and result.get("body_status") == "ok":
                fetched += 1
        except Exception:
            logger.warning("Body prefetch failed for article %d", article_id, exc_info=True)
    logger.info("Body prefetch complete: %d/%d succeeded", fetched, len(ids))
    return fetched
