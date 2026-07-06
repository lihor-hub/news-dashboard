"""Scraped-page source handler (issue #11).

Uses stdlib only (urllib + html.parser) — no extra dependencies.
Scrapers must be polite: single request, reasonable timeout, proper user-agent.
"""

from __future__ import annotations

import contextlib
import re
import urllib.request
from html.parser import HTMLParser
from typing import Any

from news_dashboard.url_safety import open_server_fetch_url, validate_server_fetch_url

USER_AGENT = "news-dashboard/0.1 (personal RSS reader; contact@lihor.ro)"
TIMEOUT_SECS = 15
# Scraped news-listing pages are rarely more than a few hundred KB; 2 MiB leaves
# headroom for verbose pages while bounding memory use and parse time for bad actors.
SCRAPE_FETCH_MAX_BYTES = 2 * 1024 * 1024


class ScrapeFetchError(RuntimeError):
    """Raised when a scraped-page fetch fails or exceeds the size cap."""


def _fetch_html(url: str, *, use_selenium: bool = False) -> str:
    validate_server_fetch_url(url)
    if use_selenium:
        from news_dashboard.selenium_client import fetch_spa_html

        return fetch_spa_html(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - scheme validated above
    with open_server_fetch_url(req, timeout=TIMEOUT_SECS) as resp:
        content_length = resp.headers.get("Content-Length")
        if content_length is not None:
            # Content-Length is attacker-controlled and may be non-numeric;
            # ignore malformed values rather than failing the fetch on them.
            with contextlib.suppress(ValueError):
                if int(content_length) > SCRAPE_FETCH_MAX_BYTES:
                    msg = (
                        f"Scraped-page response too large ({content_length} bytes, "
                        f"max {SCRAPE_FETCH_MAX_BYTES}): {url}"
                    )
                    raise ScrapeFetchError(msg)
        raw: bytes = resp.read(SCRAPE_FETCH_MAX_BYTES + 1)
        if len(raw) > SCRAPE_FETCH_MAX_BYTES:
            msg = f"Scraped-page response exceeded {SCRAPE_FETCH_MAX_BYTES} byte limit: {url}"
            raise ScrapeFetchError(msg)
        charset = resp.headers.get_content_charset("utf-8") or "utf-8"
        return raw.decode(str(charset), errors="replace")


# ──────────────────────────────────────────────
# Anthropic news page scraper
# ──────────────────────────────────────────────


class _AnthropicParser(HTMLParser):
    """Extracts article cards from https://www.anthropic.com/news.

    The page renders server-side HTML with structured card elements.
    We look for <a> tags with href=/news/<slug> that contain a heading.
    """

    def __init__(self) -> None:
        super().__init__()
        self._entries: list[dict[str, Any]] = []
        self._in_link: bool = False
        self._current_href: str = ""
        self._current_title: str = ""
        self._depth: int = 0
        self._capture_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._depth += 1
        attr_dict = dict(attrs)
        if tag == "a":
            href = attr_dict.get("href", "")
            if href and re.match(r"^/news/[^/]+$", href):
                self._in_link = True
                self._current_href = "https://www.anthropic.com" + href
                self._current_title = ""
                self._capture_depth = self._depth

    def handle_endtag(self, tag: str) -> None:  # noqa: ARG002 - signature fixed by HTMLParser
        if self._in_link and self._capture_depth == self._depth:
            if self._current_href and self._current_title.strip():
                # deduplicate by href
                existing = {e["url"] for e in self._entries}
                if self._current_href not in existing:
                    self._entries.append(
                        {
                            "url": self._current_href,
                            "title": self._current_title.strip(),
                            "description": "",
                            "date": None,
                        }
                    )
            self._in_link = False
            self._capture_depth = None
        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_link and data.strip():
            self._current_title += data

    @property
    def entries(self) -> list[dict[str, Any]]:
        return self._entries


def _scrape_anthropic(_url: str) -> list[dict[str, Any]]:
    html = _fetch_html("https://www.anthropic.com/news")
    parser = _AnthropicParser()
    parser.feed(html)
    return parser.entries[:30]


# ──────────────────────────────────────────────
# Dispatch table — add new scrapers here
# ──────────────────────────────────────────────

_SCRAPERS: dict[str, Any] = {
    "anthropic-news": _scrape_anthropic,
}


def scrape_source(source: Any) -> list[dict[str, Any]]:
    """Dispatch to the correct scraper by source slug."""
    fn = _SCRAPERS.get(source.slug)
    if fn is None:
        message = f"No scraper registered for slug '{source.slug}'"
        raise NotImplementedError(message)
    entries: list[dict[str, Any]] = fn(source.url)
    return entries
