"""Scraper tests using HTML fixtures — no live network calls."""

from __future__ import annotations

import socket
import urllib.request
from typing import Any

import pytest

from news_dashboard.scraper import (
    SCRAPE_FETCH_MAX_BYTES,
    ScrapeFetchError,
    _AnthropicParser,
    _fetch_html,
    _LinkListParser,
    scrape_source,
)
from news_dashboard.sources.service import SourceDefinition
from news_dashboard.url_safety import UnsafeUrlError, validate_server_fetch_url

# Minimal static HTML that mimics the Anthropic news page structure
ANTHROPIC_FIXTURE = """
<!DOCTYPE html>
<html>
<head><title>Anthropic News</title></head>
<body>
  <main>
    <a href="/news/claude-4-announcement">
      <h2>Claude 4 is here</h2>
      <p>Our most capable model yet.</p>
    </a>
    <a href="/news/alignment-research">
      <h2>New alignment research</h2>
    </a>
    <a href="https://external.com/other">Should not be included</a>
    <a href="/news/claude-4-announcement">Claude 4 is here (duplicate)</a>
  </main>
</body>
</html>
"""


def test_anthropic_parser_extracts_entries() -> None:
    parser = _AnthropicParser()
    parser.feed(ANTHROPIC_FIXTURE)
    entries = parser.entries
    assert len(entries) >= 2, f"expected >=2 entries, got {len(entries)}"
    urls = {e["url"] for e in entries}
    assert "https://www.anthropic.com/news/claude-4-announcement" in urls
    assert "https://www.anthropic.com/news/alignment-research" in urls


def test_anthropic_parser_deduplicates() -> None:
    parser = _AnthropicParser()
    parser.feed(ANTHROPIC_FIXTURE)
    urls = [e["url"] for e in parser.entries]
    assert len(urls) == len(set(urls)), "entries should be deduplicated by URL"


def test_anthropic_parser_excludes_external_links() -> None:
    parser = _AnthropicParser()
    parser.feed(ANTHROPIC_FIXTURE)
    for entry in parser.entries:
        assert entry["url"].startswith("https://www.anthropic.com/news/"), (
            f"unexpected URL: {entry['url']}"
        )


def test_scrape_source_uses_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceDefinition(
        "anthropic-news",
        "Anthropic News",
        "https://www.anthropic.com/news",
        "ai-llm",
        "scraped_page",
        90,
    )

    def fake_fetch(url: str) -> str:
        return ANTHROPIC_FIXTURE

    monkeypatch.setattr("news_dashboard.scraper._fetch_html", fake_fetch)
    entries = scrape_source(source)
    assert len(entries) >= 2


def test_fetch_html_rejects_private_network_url(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_open(_req: object, *, timeout: float) -> None:
        nonlocal called
        called = True
        message = "Refusing server-side fetch to unsafe host"
        raise UnsafeUrlError(message)

    monkeypatch.setattr("news_dashboard.scraper.open_server_fetch_url", fake_open)

    with pytest.raises(ValueError, match="unsafe host"):
        _fetch_html("http://127.0.0.1/admin")

    assert called is True


def test_fetch_html_selenium_path_keeps_preflight_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_fetch(_url: str) -> str:
        nonlocal called
        called = True
        return ""

    monkeypatch.setattr("news_dashboard.selenium_client.fetch_spa_html", fake_fetch)

    with pytest.raises(ValueError, match="unsafe host"):
        _fetch_html("http://127.0.0.1/admin", use_selenium=True)

    assert called is False


# Mimics Meta AI / Cohere card layout: several anchors around one post URL
# (badge, heading, CTA), some with a trailing byline of date + read time.
LINK_LIST_FIXTURE = """
<!DOCTYPE html>
<html><body>
  <a href="/blog?page=2">Next page</a>
  <a href="/blog">All posts</a>
  <div class="card">
    <a href="/blog/muse-spark-1-1"><span>FEATURED</span></a>
    <a href="/blog/muse-spark-1-1"><h4>Introducing Muse Spark 1.1</h4></a>
    <a href="/blog/muse-spark-1-1">Learn More</a>
  </div>
  <div class="card">
    <a href="/blog/north-mini-code?ref=home">Learn more</a>
    <a href="/blog/north-mini-code">
      <img src="/x.png" alt="">
      Introducing North Mini Code: Cohere's first model Jun 09, 2026 3 min read
    </a>
  </div>
  <a href="https://external.example.com/blog/other">Off-site post</a>
  <a href="/blog/no-title-here"><img src="/y.png" alt=""></a>
</body></html>
"""


def test_link_list_parser_keeps_longest_title_per_url() -> None:
    parser = _LinkListParser("https://ai.meta.com/blog/", r"^/blog/[^/]+/?$")
    parser.feed(LINK_LIST_FIXTURE)
    by_url = {e["url"]: e["title"] for e in parser.entries}
    assert by_url["https://ai.meta.com/blog/muse-spark-1-1"] == "Introducing Muse Spark 1.1"


def test_link_list_parser_strips_card_byline() -> None:
    parser = _LinkListParser("https://cohere.com/blog", r"^/blog/[^/]+$")
    parser.feed(LINK_LIST_FIXTURE)
    by_url = {e["url"]: e["title"] for e in parser.entries}
    assert (
        by_url["https://cohere.com/blog/north-mini-code"]
        == "Introducing North Mini Code: Cohere's first model"
    )


def test_link_list_parser_dedupes_and_strips_query() -> None:
    parser = _LinkListParser("https://cohere.com/blog", r"^/blog/[^/]+$")
    parser.feed(LINK_LIST_FIXTURE)
    urls = [e["url"] for e in parser.entries]
    assert urls == sorted(set(urls), key=urls.index), "entries should be deduped by URL"
    assert "https://cohere.com/blog/north-mini-code" in urls
    assert all("?" not in u for u in urls), "query strings should be stripped"


def test_link_list_parser_excludes_listing_and_offsite_links() -> None:
    parser = _LinkListParser("https://ai.meta.com/blog/", r"^/blog/[^/]+/?$")
    parser.feed(LINK_LIST_FIXTURE)
    urls = {e["url"] for e in parser.entries}
    assert "https://ai.meta.com/blog/" not in urls
    assert not any("external.example.com" in u for u in urls)
    assert not any(u.endswith("/blog") for u in urls)


def test_link_list_parser_falls_back_to_slug_title() -> None:
    parser = _LinkListParser("https://ai.meta.com/blog/", r"^/blog/[^/]+/?$")
    parser.feed(LINK_LIST_FIXTURE)
    by_url = {e["url"]: e["title"] for e in parser.entries}
    assert by_url["https://ai.meta.com/blog/no-title-here"] == "No Title Here"


@pytest.mark.parametrize("slug", ["cohere-blog", "meta-ai-blog"])
def test_registered_scrapers_use_fetch(slug: str, monkeypatch: pytest.MonkeyPatch) -> None:
    source = SourceDefinition(slug, slug, "https://example.com", "ai-llm", "scraped_page", 80)
    monkeypatch.setattr("news_dashboard.scraper._fetch_html", lambda _url: LINK_LIST_FIXTURE)
    entries = scrape_source(source)
    assert entries, "expected at least one scraped entry"
    assert all(e["title"] for e in entries)


def test_scrape_source_unknown_slug_raises() -> None:
    source = SourceDefinition(
        "no-scraper", "No Scraper", "https://example.com", "python", "scraped_page", 50
    )
    with pytest.raises(NotImplementedError, match="no-scraper"):
        scrape_source(source)


def test_every_scraped_page_source_has_a_registered_scraper() -> None:
    """Guard against re-adding a scraped_page source with no scraper (issue #1142)."""
    from news_dashboard.scraper import _SCRAPERS
    from news_dashboard.sources.service import DEFAULT_SOURCES

    missing = [
        s.slug for s in DEFAULT_SOURCES if s.kind == "scraped_page" and s.slug not in _SCRAPERS
    ]
    assert not missing, f"scraped_page sources without a scraper: {missing}"


class _FakeHeaders:
    def __init__(self, content_length: str | None) -> None:
        self._content_length = content_length

    def get(self, name: str, default: Any = None) -> Any:
        if name == "Content-Length":
            return self._content_length
        return default

    def get_content_charset(self, default: str = "utf-8") -> str:
        return default


class _FakeResponse:
    def __init__(self, body: bytes, content_length: str | None) -> None:
        self._body = body
        self.headers = _FakeHeaders(content_length)

    def read(self, amt: int | None = None) -> bytes:
        if amt is None:
            return self._body
        return self._body[:amt]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def test_fetch_html_resolves_hostname_once(monkeypatch: pytest.MonkeyPatch) -> None:
    resolutions: list[tuple[str, int]] = []

    def fake_getaddrinfo(
        host: str,
        port: int,
        **_kwargs: object,
    ) -> list[tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]]:
        resolutions.append((host, port))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    def fake_open(req: object, *, timeout: float) -> _FakeResponse:
        assert isinstance(req, urllib.request.Request)
        validate_server_fetch_url(req.full_url)
        return _FakeResponse(b"<html>ok</html>", None)

    monkeypatch.setattr("news_dashboard.url_safety.socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("news_dashboard.scraper.open_server_fetch_url", fake_open)

    assert _fetch_html("https://example.com/news") == "<html>ok</html>"
    assert resolutions == [("example.com", 443)]


def test_fetch_html_under_limit_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"<html>hello</html>"
    monkeypatch.setattr(
        "news_dashboard.scraper.open_server_fetch_url",
        lambda _req, **_kwargs: _FakeResponse(body, str(len(body))),
    )
    html = _fetch_html("https://example.com/news")
    assert html == "<html>hello</html>"


def test_fetch_html_rejects_oversized_content_length(monkeypatch: pytest.MonkeyPatch) -> None:
    read_called = False

    class _NoReadResponse(_FakeResponse):
        def read(self, amt: int | None = None) -> bytes:
            nonlocal read_called
            read_called = True
            return super().read(amt)

    monkeypatch.setattr(
        "news_dashboard.scraper.open_server_fetch_url",
        lambda _req, **_kwargs: _NoReadResponse(b"x", str(SCRAPE_FETCH_MAX_BYTES + 1)),
    )
    with pytest.raises(ScrapeFetchError, match="too large"):
        _fetch_html("https://example.com/news")
    assert read_called is False


def test_fetch_html_rejects_body_over_limit_without_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oversized_body = b"x" * (SCRAPE_FETCH_MAX_BYTES + 100)
    monkeypatch.setattr(
        "news_dashboard.scraper.open_server_fetch_url",
        lambda _req, **_kwargs: _FakeResponse(oversized_body, None),
    )
    with pytest.raises(ScrapeFetchError, match="exceeded"):
        _fetch_html("https://example.com/news")
