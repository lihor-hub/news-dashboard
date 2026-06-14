"""Scraped-page source handler (issue #11).

Uses stdlib only (urllib + html.parser) — no extra dependencies.
Scrapers must be polite: single request, reasonable timeout, proper user-agent.
"""

from __future__ import annotations

import re
import urllib.request
from html.parser import HTMLParser
from typing import Any

USER_AGENT = "news-dashboard/0.1 (personal RSS reader; contact@example.com)"
TIMEOUT_SECS = 15


def _fetch_html(url: str) -> str:
    if not url.startswith(("http:", "https:")):
        message = f"Refusing to fetch non-HTTP URL: {url!r}"
        raise ValueError(message)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - scheme validated above
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:  # noqa: S310 - scheme validated above
        raw: bytes = resp.read()
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
