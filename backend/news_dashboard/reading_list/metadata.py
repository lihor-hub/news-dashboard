"""Fetch and parse metadata (OpenGraph / oEmbed) for reading list URLs."""

from __future__ import annotations

import json
import urllib.request
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlencode, urlparse

from news_dashboard.url_safety import open_server_fetch_url

USER_AGENT = "news-dashboard/0.1 (personal RSS reader; contact@lihor.ro)"
TIMEOUT_SECS = 15
_MAX_BYTES = 1_000_000

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_YOUTUBE_CHANNEL_PREFIXES = ("/@", "/channel/", "/c/", "/user/")


def detect_kind(url: str) -> str:
    """Classify a URL as video, channel, or article."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        return "article"
    if host == "youtu.be":
        return "video"
    if parsed.path.startswith(_YOUTUBE_CHANNEL_PREFIXES):
        return "channel"
    return "video"


class _MetaParser(HTMLParser):
    """Collect OpenGraph / Twitter-card meta tags and the <title> text."""

    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
            return
        if tag != "meta":
            return
        attr_map = {name: value for name, value in attrs if value is not None}
        key = attr_map.get("property") or attr_map.get("name")
        content = attr_map.get("content")
        if key and content and key.lower() not in self.meta:
            self.meta[key.lower()] = content

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)


def parse_html_metadata(html: str) -> dict[str, Any]:
    """Extract title/description/image/site name from an HTML document."""
    parser = _MetaParser()
    parser.feed(html)
    meta = parser.meta
    page_title = "".join(parser.title_parts).strip() or None
    return {
        "title": meta.get("og:title") or meta.get("twitter:title") or page_title,
        "description": (
            meta.get("og:description") or meta.get("twitter:description") or meta.get("description")
        ),
        "image_url": meta.get("og:image") or meta.get("twitter:image"),
        "site_name": meta.get("og:site_name"),
    }


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - scheme validated by open_server_fetch_url
    with open_server_fetch_url(req, timeout=TIMEOUT_SECS) as resp:
        raw: bytes = resp.read(_MAX_BYTES)
    return raw.decode("utf-8", errors="replace")


def _fetch_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - scheme validated by open_server_fetch_url
    with open_server_fetch_url(req, timeout=TIMEOUT_SECS) as resp:
        raw: bytes = resp.read(_MAX_BYTES)
    payload = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        message = f"Unexpected oEmbed payload for {url!r}"
        raise TypeError(message)
    return payload


def fetch_url_metadata(url: str) -> dict[str, Any]:
    """Fetch preview metadata for a URL.

    YouTube videos go through the keyless oEmbed endpoint; everything else is
    fetched as HTML and parsed for OpenGraph/Twitter-card tags.
    """
    kind = detect_kind(url)
    if kind == "video":
        oembed_url = "https://www.youtube.com/oembed?" + urlencode({"url": url, "format": "json"})
        payload = _fetch_json(oembed_url)
        return {
            "title": payload.get("title"),
            "description": payload.get("author_name"),
            "image_url": payload.get("thumbnail_url"),
            "site_name": "YouTube",
            "kind": kind,
        }
    parsed = parse_html_metadata(_fetch_html(url))
    return {**parsed, "kind": kind}
