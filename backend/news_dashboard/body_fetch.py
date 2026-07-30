"""Fetch and cache article body text on first reader open (issue #79).

Uses stdlib only (urllib + html.parser) — no extra dependencies.
Extracted text is stored in articles.body / articles.body_status.
Subsequent opens serve the cache; no bulk crawling at ingest.
"""

from __future__ import annotations

import logging
import os
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from news_dashboard.article_visibility import get_visible_article_row
from news_dashboard.content_extraction import (
    ExtractionAttempt,
    ExtractionMethod,
    ExtractionResult,
    FailureReason,
    assess_extracted_text,
)
from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.scraper import TIMEOUT_SECS, USER_AGENT
from news_dashboard.social_posts import canonical_x_status_url
from news_dashboard.url_safety import (
    UnsafeUrlError,
    open_server_fetch_url,
)

logger = logging.getLogger(__name__)

_AI_HTML_LIMIT = 15_000
# Raw bytes downloaded from the network before decoding, well above _AI_HTML_LIMIT
# to tolerate multi-byte charsets while still bounding worst-case memory/network use.
_AI_FETCH_BYTE_CAP = 200_000
_AI_MODEL = "gpt-4o-mini"
_AI_PROMPT = (
    "Extract the main article text from this HTML. "
    "Return only the article body as plain text, no HTML tags.\n\n{{html}}"
)


def _server_fetch_request(url: str) -> urllib.request.Request:
    try:
        return urllib.request.Request(  # noqa: S310 - scheme validated by central opener
            url,
            headers={"User-Agent": USER_AGENT},
        )
    except ValueError as exc:
        message = f"Refusing server-side fetch to malformed URL: {url!r}"
        raise UnsafeUrlError(message) from exc


def _fetch_capped_html(url: str, *, byte_cap: int) -> str:
    """Stream ``url`` and decode at most ``byte_cap`` bytes of the response body.

    Stops reading as soon as the cap is reached instead of downloading the
    full response before truncating, so a large HTML page can't be pulled
    entirely into memory just to be sliced down afterward.
    """
    request = _server_fetch_request(url)
    with open_server_fetch_url(request, timeout=15) as response:
        charset = response.headers.get_content_charset("utf-8") or "utf-8"
        raw: bytes = response.read(byte_cap)
    return raw.decode(str(charset), errors="replace")


def _ai_extract_body(url: str, *, user_id: int | None = None) -> tuple[str, str]:
    """Fetch bounded HTML centrally and extract body text via the free LLM gateway.

    Returns (text, 'ok') on success or ('', 'error') if no API key is
    configured, the HTTP fetch fails, or the AI call fails.
    """
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        return "", "error"

    model = os.getenv("OPENAI_BRIEFING_MODEL", _AI_MODEL)

    try:
        html = _fetch_capped_html(url, byte_cap=_AI_FETCH_BYTE_CAP)[:_AI_HTML_LIMIT]
    except UnsafeUrlError as exc:
        logger.warning("ai_body_fetch: unsafe URL %r: %s", url, exc)
        return "", "error"
    except Exception as exc:
        logger.warning("ai_body_fetch: HTTP fetch failed for %r: %s", url, exc)
        return "", "error"

    try:
        from langchain_core.messages import HumanMessage
        from langchain_core.prompt_values import ChatPromptValue
        from langfuse import propagate_attributes

        from news_dashboard.ai_client import (
            get_chat_model,
            get_prompt,
            langfuse_enabled,
            response_text,
        )

        chat_model = get_chat_model(
            api_key=api_key, base_url=base_url, model=model, max_tokens=2048
        )
        prompt = get_prompt(
            "ai-body-fetch",
            fallback=_AI_PROMPT,
            prompt_type="text",
            label="production",
            variables={"html": html},
        )
        callbacks: list[Any] = []
        if langfuse_enabled():
            from langfuse.langchain import CallbackHandler

            callbacks.append(CallbackHandler())
        with propagate_attributes(
            user_id=str(user_id) if user_id is not None else None,
            tags=["body-fetch"],
            trace_name="ai-body-fetch",
            prompt=prompt.langfuse_prompt,
        ):
            result = chat_model.invoke(
                ChatPromptValue(messages=[HumanMessage(content=prompt.text)]),
                config={"callbacks": callbacks},
            )
        text = response_text(result).strip()
        if not text:
            return "", "error"
        logger.info("ai_body_fetch: AI extraction succeeded for %r", url)
        return text, "ok"
    except Exception as exc:
        logger.warning("ai_body_fetch: AI extraction failed for %r: %s", url, exc)
        return "", "error"


# Minimum length (chars) of normalized Crawl4AI output to treat as a real body.
_CRAWL4AI_MIN_LEN = 40


def _normalize_crawl4ai_result(result: Any) -> str:
    """Pick the best text field from a Crawl4AI result and normalize it.

    Crawl4AI exposes several candidate fields; prefer cleaned article Markdown
    (``markdown.fit_markdown``), then raw Markdown, then a plain-string
    ``markdown``, then ``extracted_content``, then ``cleaned_html``. Returns an
    empty string when none carry usable text.
    """
    candidate = ""
    markdown = getattr(result, "markdown", None)
    if markdown is not None:
        for attr in ("fit_markdown", "raw_markdown"):
            value = getattr(markdown, attr, None)
            if isinstance(value, str) and value.strip():
                candidate = value
                break
        else:
            if isinstance(markdown, str):
                candidate = markdown
    for attr in ("extracted_content", "cleaned_html"):
        if candidate.strip():
            break
        value = getattr(result, attr, None)
        if isinstance(value, str):
            candidate = value
    return _normalize_body_text(candidate)


def _normalize_body_text(text: str) -> str:
    """Trim trailing whitespace and collapse blank-line runs, preserving paragraphs."""
    if not text:
        return ""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _run_crawl4ai(url: str) -> Any:
    """Run Crawl4AI against ``url`` and return its CrawlResult.

    Kept separate so tests can patch it without importing the optional
    dependency. Raises ImportError when Crawl4AI is not installed.
    """
    import asyncio
    import importlib

    # Dynamic import keeps the optional dependency out of static type resolution;
    # ModuleNotFoundError (an ImportError) is raised and handled when it's absent.
    crawler_cls = importlib.import_module("crawl4ai").AsyncWebCrawler

    async def _crawl() -> Any:
        async with crawler_cls() as crawler:
            return await crawler.arun(url=url)

    return asyncio.run(_crawl())


def _crawl4ai_extract_body(_url: str) -> tuple[str, str]:
    """Deterministic Crawl4AI-backed extraction, tried before the LLM fallback.

    Enforces the same SSRF/scheme boundary as the other fetchers via
    ``validate_server_fetch_url`` before launching a browser. Returns
    ``(text, 'ok')`` when Crawl4AI yields meaningful article text/Markdown, or
    ``('', 'error')`` for unsafe URLs, a missing dependency, or any
    fetch/parse failure.
    """
    # Crawl4AI owns its browser networking and does not currently expose the
    # per-request interception used by selenium_client. Launching it for a
    # user-controlled URL could therefore follow a redirect or JS request into
    # a private network. Keep the stage fail-closed until equivalent request
    # interception is available.
    logger.info("crawl4ai_body_fetch: disabled because request interception is unavailable")
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
        self._skip_tag: str | None = None
        self._skip_tag_depth = 0
        self._chunks: list[str] = []
        self._current: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        if self._skip_tag is not None:
            if tag == self._skip_tag:
                self._skip_tag_depth += 1
            return
        if tag in _SKIP_TAGS:
            self._skip_tag = tag
            self._skip_tag_depth = 1
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if self._skip_tag is not None:
            if tag == self._skip_tag:
                self._skip_tag_depth -= 1
                if self._skip_tag_depth == 0:
                    self._skip_tag = None
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_tag is not None:
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


def _selenium_extract_body(url: str) -> tuple[str, str]:
    """Fallback: fetch via headless browser and extract body text.

    Returns ('', 'error') if selenium is unavailable or rendering fails.
    """
    try:
        from news_dashboard.selenium_client import fetch_spa_html

        html = fetch_spa_html(url)
    except ImportError:
        return "", "error"
    except Exception as exc:
        logger.warning("selenium_body_fetch: fetch failed for %r: %s", url, exc)
        return "", "error"

    try:
        parser = _BodyExtractor()
        parser.feed(html)
        text = parser.result()
    except Exception as exc:
        logger.warning("selenium_body_fetch: parse failed for %r: %s", url, exc)
        return "", "error"

    if not text.strip():
        return "", "error"

    return text, "ok"


def _static_extract_body(  # noqa: PLR0911 - each bounded fetch failure has a distinct reason
    url: str,
) -> tuple[str, str, FailureReason | None]:
    """Fetch and parse static HTML without invoking a rendered fallback."""
    try:
        req = _server_fetch_request(url)
        with open_server_fetch_url(req, timeout=TIMEOUT_SECS) as resp:
            content_type = resp.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                return "", "error", "non_html"
            raw: bytes = resp.read(500_000)  # cap at ~500 KB
            charset = resp.headers.get_content_charset("utf-8") or "utf-8"
            html = raw.decode(str(charset), errors="replace")
    except UnsafeUrlError as exc:
        logger.warning("body_fetch: unsafe URL %r: %s", url, exc)
        return "", "error", "unsafe_url"
    except urllib.error.HTTPError as exc:
        logger.warning("body_fetch: HTTP %d for %r", exc.code, url)
        if exc.code == 404:
            return "", "error", "not_found"
        if exc.code in {403, 429}:
            return "", "error", "blocked"
        return "", "error", "fetch_failed"
    except Exception as exc:
        logger.warning("body_fetch: fetch failed for %r: %s", url, exc)
        return "", "error", "fetch_failed"

    try:
        parser = _BodyExtractor()
        parser.feed(html)
        text = parser.result()
    except Exception as exc:
        logger.warning("body_fetch: parse failed for %r: %s", url, exc)
        return "", "error", "no_readable_content"

    if not text.strip():
        return "", "error", "no_readable_content"

    return text, "ok", None


def _attempt_extraction(
    method: ExtractionMethod,
    func: Any,
    *args: Any,
    **kwargs: Any,
) -> tuple[str, ExtractionAttempt]:
    started = time.monotonic()
    body, status = func(*args, **kwargs)
    latency_ms = int((time.monotonic() - started) * 1000)
    if status != "ok" or not body.strip():
        reason: FailureReason = "render_failed" if method == "selenium" else "fetch_failed"
        return "", ExtractionAttempt(
            method=method,
            status="failed",
            latency_ms=latency_ms,
            failure_reason=reason,
            detail=f"{method} returned status={status!r}",
        )

    quality = assess_extracted_text(body)
    return body, ExtractionAttempt(
        method=method,
        status="accepted" if quality.accepted else "rejected",
        latency_ms=latency_ms,
        quality=quality,
        failure_reason=None if quality.accepted else "no_readable_content",
        detail=None if quality.accepted else ",".join(quality.rejection_reasons),
    )


def extract_public_content(
    url: str,
    *,
    user_id: int | None = None,
    allow_ai: bool = True,
    allow_crawl4ai: bool = True,
) -> ExtractionResult:
    """Extract meaningful public web content through ordered bounded fallbacks."""
    attempts: list[ExtractionAttempt] = []

    started = time.monotonic()
    body, status, failure_reason = _static_extract_body(url)
    latency_ms = int((time.monotonic() - started) * 1000)
    if status == "ok":
        quality = assess_extracted_text(body)
        static_attempt = ExtractionAttempt(
            method="static",
            status="accepted" if quality.accepted else "rejected",
            latency_ms=latency_ms,
            quality=quality,
            failure_reason=None if quality.accepted else "no_readable_content",
            detail=None if quality.accepted else ",".join(quality.rejection_reasons),
        )
        attempts.append(static_attempt)
        if quality.accepted:
            return ExtractionResult.success(
                text=body,
                method="static",
                quality=quality,
                attempts=tuple(attempts),
            )
    else:
        reason = failure_reason or "fetch_failed"
        attempts.append(
            ExtractionAttempt(
                method="static",
                status="failed",
                latency_ms=latency_ms,
                failure_reason=reason,
                detail=f"static extraction failed: {reason}",
            )
        )
        if reason in {"unsafe_url", "not_found", "non_html"}:
            return ExtractionResult.failure(failure_reason=reason, attempts=tuple(attempts))

    body, attempt = _attempt_extraction("selenium", _selenium_extract_body, url)
    attempts.append(attempt)
    if attempt.status == "accepted" and attempt.quality is not None:
        return ExtractionResult.success(
            text=body,
            method="selenium",
            quality=attempt.quality,
            attempts=tuple(attempts),
        )

    if allow_crawl4ai:
        body, attempt = _attempt_extraction("crawl4ai", _crawl4ai_extract_body, url)
        attempts.append(attempt)
        if attempt.status == "accepted" and attempt.quality is not None:
            return ExtractionResult.success(
                text=body,
                method="crawl4ai",
                quality=attempt.quality,
                attempts=tuple(attempts),
            )

    if allow_ai:
        body, attempt = _attempt_extraction("ai", _ai_extract_body, url, user_id=user_id)
        attempts.append(attempt)
        if attempt.status == "accepted" and attempt.quality is not None:
            return ExtractionResult.success(
                text=body,
                method="ai",
                quality=attempt.quality,
                attempts=tuple(attempts),
            )

    final_reason: FailureReason = "no_readable_content"
    for item in attempts:
        if item.failure_reason in {"blocked", "unsafe_url", "not_found", "non_html"}:
            final_reason = item.failure_reason
            break
    return ExtractionResult.failure(failure_reason=final_reason, attempts=tuple(attempts))


def extract_body(url: str) -> tuple[str, str]:
    """Compatibility wrapper for quality-gated static and Selenium extraction."""
    result = extract_public_content(url, allow_ai=False, allow_crawl4ai=False)
    if result.status == "ok":
        return result.text, "ok"

    return "", "error"


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


def _merge_user_recommendation(
    d: dict[str, Any], conn: Any, article_id: int, user_id: int
) -> dict[str, Any]:
    """Overlay the per-user recommendation score/signals onto an article dict.

    Mirrors the recommendation columns ``list_articles`` returns so the
    single-article read path exposes the same ``recommendation_score`` /
    ``recommendation_model`` / ``recommendation_signals`` fields. Absent metadata
    (no stored score yet) leaves the fields ``None`` so the frontend falls back to
    its cold-start explanation rather than a stale one.
    """
    rec_row = conn.execute(
        "SELECT recommendation_score, model_version, signals, explanation"
        " FROM user_article_recommendations WHERE user_id = %s AND article_id = %s",
        (user_id, article_id),
    ).fetchone()
    rec = row_to_dict(rec_row) if rec_row else None
    score = rec.get("recommendation_score") if rec else None
    d["recommendation_score"] = float(score) if score is not None else None
    d["recommendation_model"] = rec.get("model_version") if rec else None
    d["recommendation_signals"] = rec.get("signals") if rec else None
    d["recommendation_explanation"] = rec.get("explanation") if rec else None
    return d


def _article_from_row(row: Any, conn: Any, article_id: int, user_id: int | None) -> dict[str, Any]:
    d = row_to_dict(row)
    d.pop("embedding_vec", None)
    d.pop("fts_vector", None)
    if d.get("kind") == "nitter_feed":
        d["url"] = canonical_x_status_url(str(d.get("url") or ""))
    if user_id is not None:
        _merge_user_state(d, conn, article_id, user_id)
        _merge_user_recommendation(d, conn, article_id, user_id)
    return d


def _complete_stored_nitter_post(article: dict[str, Any]) -> str:
    """Select complete feed-derived text without accepting truncated UI copy."""
    for field in ("summary", "title"):
        candidate = str(article.get(field) or "").strip()
        if candidate and candidate != "Untitled" and not candidate.endswith(("…", "...")):
            return candidate
    return ""


def get_article(
    article_id: int,
    db_path: Path | str | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Fetch a single article by ID, stripping internal columns.

    When user_id is given the article must be visible to that user
    (global source not disabled, or private source owned by the user).
    Returns None for invisible articles as well as non-existent ones.
    Per-user state from user_article_state is merged in for the returned dict.
    """
    init_db(db_path)
    with connect(db_path) as conn:
        row = get_visible_article_row(conn, article_id, user_id)
        if row is None:
            return None
        return _article_from_row(row, conn, article_id, user_id)


def translate_body(body: str, from_lang: str) -> str:
    """Translate the body text to English using the free LLM gateway."""
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key or not body.strip():
        return body

    try:
        from langchain_core.messages import SystemMessage
        from langchain_core.prompts import ChatPromptTemplate
        from langfuse import propagate_attributes

        from news_dashboard.ai_client import get_chat_model, langfuse_enabled, response_text

        prompt = (
            f"You are a translation assistant. Translate the following body text from "
            f"language code '{from_lang}' to English. Return only the translated plain text, "
            f"preserving paragraph breaks, and no additional commentary."
        )

        chat_model = get_chat_model(
            api_key=api_key,
            base_url=base_url,
            model="gpt-4o-mini",
            max_tokens=2048,
            temperature=0.0,
        )
        callbacks: list[Any] = []
        if langfuse_enabled():
            from langfuse.langchain import CallbackHandler

            callbacks.append(CallbackHandler())
        template = ChatPromptTemplate.from_messages(
            [SystemMessage(content=prompt), ("human", "{body}")]
        )
        with propagate_attributes(tags=["translation"], trace_name="translate-body"):
            result = (template | chat_model).invoke({"body": body}, config={"callbacks": callbacks})
        translated = response_text(result).strip()
        if translated:
            return translated
    except Exception as exc:
        logger.warning("Failed to translate body: %s", exc)
    return body


def fetch_and_cache_body(
    article_id: int,
    db_path: Path | str | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Fetch and store body for an article. Returns the updated article dict or None if not found.

    If body_status is already 'ok', returns the cached row immediately.
    When user_id is given the returned dict reflects per-user state.
    """
    init_db(db_path)
    with connect(db_path) as conn:
        row = get_visible_article_row(conn, article_id, user_id)
        if row is None:
            return None
        row_d = row_to_dict(row)
        if row_d.get("body_status") == "ok":
            return _article_from_row(row, conn, article_id, user_id)
        if row_d.get("kind") == "nitter_feed":
            stored_post = _complete_stored_nitter_post(row_d)
            if stored_post:
                conn.execute(
                    """
                    UPDATE articles
                       SET body = %s,
                           original_body = %s,
                           body_status = 'ok',
                           updated_at = CURRENT_TIMESTAMP
                     WHERE id = %s
                    """,
                    (
                        stored_post,
                        row_d.get("original_title")
                        if row_d.get("detected_lang") not in {None, "en"}
                        else None,
                        article_id,
                    ),
                )
                row_d["body"] = stored_post
                row_d["original_body"] = (
                    row_d.get("original_title")
                    if row_d.get("detected_lang") not in {None, "en"}
                    else None
                )
                row_d["body_status"] = "ok"
                return _article_from_row(row_d, conn, article_id, user_id)

    url = row_d["url"]
    extraction: Any = (
        extract_public_content(url, user_id=user_id)
        if user_id is not None
        else extract_public_content(url)
    )
    if isinstance(extraction, ExtractionResult):
        body, status = extraction.text, extraction.status
    else:
        body, status = extraction

    original_body = None
    detected_lang = row_d.get("detected_lang") or "en"
    if status == "ok" and detected_lang != "en":
        original_body = body
        body = translate_body(body, detected_lang)

    with connect(db_path) as conn:
        conn.execute(
            "UPDATE articles SET body = %s, original_body = %s, body_status = %s,"
            " updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (body if status == "ok" else None, original_body, status, article_id),
        )

    return get_article(article_id, db_path=db_path, user_id=user_id)


def prefetch_article_bodies(limit: int = 20, db_path: Path | str | None = None) -> int:
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
