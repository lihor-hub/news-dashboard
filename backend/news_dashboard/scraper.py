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
from urllib.parse import urljoin, urlparse

from news_dashboard.url_safety import (
    UnsafeUrlError,
    open_server_fetch_url,
    validate_server_fetch_url,
)

USER_AGENT = "news-dashboard/0.1 (personal RSS reader; contact@lihor.ro)"
TIMEOUT_SECS = 15
# Scraped news-listing pages are rarely more than a few hundred KB; 2 MiB leaves
# headroom for verbose pages while bounding memory use and parse time for bad actors.
SCRAPE_FETCH_MAX_BYTES = 2 * 1024 * 1024


class ScrapeFetchError(RuntimeError):
    """Raised when a scraped-page fetch fails or exceeds the size cap."""


def _fetch_html(url: str, *, use_selenium: bool = False) -> str:
    if use_selenium:
        validate_server_fetch_url(url)
        from news_dashboard.selenium_client import (
            fetch_spa_html,
            public_renderer_egress_proxy,
        )

        try:
            proxy = public_renderer_egress_proxy()
        except ValueError as exc:
            message = "Public renderer egress proxy configuration is invalid"
            raise ScrapeFetchError(message) from exc
        if proxy is None:
            message = "Public renderer requires a validating egress proxy"
            raise ScrapeFetchError(message)
        return fetch_spa_html(url)
    try:
        req = urllib.request.Request(  # noqa: S310 - scheme validated by central opener
            url, headers={"User-Agent": USER_AGENT}
        )
    except ValueError as exc:
        message = f"Refusing server-side fetch to malformed URL: {url!r}"
        raise UnsafeUrlError(message) from exc
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
# Generic listing-page scraper
# ──────────────────────────────────────────────


def _slug_title(url: str) -> str:
    """Fallback title derived from the final path segment of an article URL."""
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ").strip().title() or "Untitled"


# Card layouts wrap several anchors around one post URL (a badge, a "Learn more"
# CTA, the heading). The heading is reliably the longest, so keep the longest
# text per URL. Titles often carry a trailing "<Mon> <D>, <YYYY> … min read"
# byline from the card chrome — strip it so stored titles stay clean.
_CARD_BYLINE_RE = re.compile(
    r"\s+[A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4}\b.*?\bmin read\b\s*$",
    re.IGNORECASE,
)


class _LinkListParser(HTMLParser):
    """Extract article links from a blog/news listing page.

    Collects anchors whose (resolved) path matches ``path_pattern`` and keeps,
    per URL, the longest anchor text seen — which is the post title rather than a
    badge or CTA that links to the same post. Anchors do not nest in valid HTML,
    so a simple in-anchor flag is robust to void elements (``<img>``) inside a
    card, unlike depth counting.
    """

    def __init__(self, base_url: str, path_pattern: str) -> None:
        super().__init__()
        self._base = base_url
        self._base_host = urlparse(base_url).netloc
        self._path_re = re.compile(path_pattern)
        self._titles: dict[str, str] = {}
        self._order: list[str] = []
        self._href: str = ""
        self._text: str = ""
        self._capturing: bool = False

    def _resolve(self, href: str) -> str:
        """Return the absolute, query-stripped URL if it matches the pattern, else ''."""
        if not href:
            return ""
        absolute = urljoin(self._base, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            return ""
        if parsed.netloc != self._base_host:
            return ""
        clean = parsed._replace(query="", fragment="").geturl()
        if not self._path_re.match(parsed.path):
            return ""
        return clean

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        resolved = self._resolve(dict(attrs).get("href") or "")
        self._capturing = bool(resolved)
        self._href = resolved
        self._text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._capturing:
            return
        text = re.sub(r"\s+", " ", self._text).strip()
        text = _CARD_BYLINE_RE.sub("", text).strip()
        if self._href not in self._titles:
            self._order.append(self._href)
        if len(text) > len(self._titles.get(self._href, "")):
            self._titles[self._href] = text
        self._capturing = False
        self._href = ""
        self._text = ""

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._text += data

    @property
    def entries(self) -> list[dict[str, Any]]:
        return [
            {
                "url": url,
                "title": self._titles.get(url) or _slug_title(url),
                "description": "",
                "date": None,
            }
            for url in self._order
        ]


def _scrape_link_list(page_url: str, path_pattern: str, *, limit: int = 30) -> list[dict[str, Any]]:
    html = _fetch_html(page_url)
    parser = _LinkListParser(page_url, path_pattern)
    parser.feed(html)
    return parser.entries[:limit]


def _scrape_cohere(_url: str) -> list[dict[str, Any]]:
    return _scrape_link_list("https://cohere.com/blog", r"^/blog/[^/]+$")


def _scrape_meta(_url: str) -> list[dict[str, Any]]:
    return _scrape_link_list("https://ai.meta.com/blog/", r"^/blog/[^/]+/?$")


# ──────────────────────────────────────────────
# Dispatch table — add new scrapers here
# ──────────────────────────────────────────────

_SCRAPERS: dict[str, Any] = {
    "anthropic-news": _scrape_anthropic,
    "cohere-blog": _scrape_cohere,
    "meta-ai-blog": _scrape_meta,
}


def scrape_source(source: Any) -> list[dict[str, Any]]:
    """Dispatch to the correct scraper by source slug."""
    fn = _SCRAPERS.get(source.slug)
    if fn is None:
        message = f"No scraper registered for slug '{source.slug}'"
        raise NotImplementedError(message)
    entries: list[dict[str, Any]] = fn(source.url)
    return entries
