"""Scraper tests using HTML fixtures — no live network calls."""

from __future__ import annotations

import pytest

from news_dashboard.scraper import _AnthropicParser, scrape_source
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


def test_scrape_source_unknown_slug_raises() -> None:
    source = SourceDefinition(
        "no-scraper", "No Scraper", "https://example.com", "python", "scraped_page", 50
    )
    with pytest.raises(NotImplementedError, match="no-scraper"):
        scrape_source(source)
