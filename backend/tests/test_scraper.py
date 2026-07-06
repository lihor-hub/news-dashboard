"""Scraper tests using HTML fixtures — no live network calls."""

from __future__ import annotations

from typing import Any

import pytest

from news_dashboard.scraper import (
    SCRAPE_FETCH_MAX_BYTES,
    ScrapeFetchError,
    _AnthropicParser,
    _fetch_html,
    scrape_source,
)
from news_dashboard.sources import SourceDefinition

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

    def fake_urlopen(_req: object, timeout: float) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="unsafe host"):
        _fetch_html("http://127.0.0.1/admin")

    assert called is False


def test_scrape_source_unknown_slug_raises() -> None:
    source = SourceDefinition(
        "no-scraper", "No Scraper", "https://example.com", "python", "scraped_page", 50
    )
    with pytest.raises(NotImplementedError, match="no-scraper"):
        scrape_source(source)


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
