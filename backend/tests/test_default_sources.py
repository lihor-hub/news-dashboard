"""Keep the built-in source catalog valid for onboarding and ingestion."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from news_dashboard.ingest.service import _fetch_entries_by_kind
from news_dashboard.onboarding.service import interest_options
from news_dashboard.sources.service import DEFAULT_SOURCES, SourceDefinition


def test_default_sources_have_unique_slugs() -> None:
    """Every DEFAULT_SOURCES slug appears exactly once.

    A duplicate slug lets ingest_all() fetch the same built-in source twice
    in one run and lets onboarding recommendations offer duplicate candidates,
    even though PostgreSQL upserts converge on a single sources row.
    """
    slugs = [source.slug for source in DEFAULT_SOURCES]
    counts = Counter(slugs)
    duplicates = {slug: count for slug, count in counts.items() if count > 1}
    assert not duplicates, f"duplicate DEFAULT_SOURCES slugs: {duplicates}"


def test_default_source_interest_tags_are_selectable() -> None:
    allowed = interest_options()
    offenders = {
        source.slug: sorted(set(source.interest_tags) - allowed)
        for source in DEFAULT_SOURCES
        if set(source.interest_tags) - allowed
    }
    assert not offenders, f"unselectable DEFAULT_SOURCES interest tags: {offenders}"


@pytest.mark.parametrize("source", DEFAULT_SOURCES, ids=lambda source: source.slug)
def test_default_source_kind_dispatches_without_network(
    source: SourceDefinition, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Unknown kinds currently fall back to RSS, so exercise dispatch as well as
    # rejecting catalog typos that the permissive fallback would otherwise hide.
    assert source.kind in {
        "rss_feed",
        "github_release_feed",
        "trending_feed",
        "scraped_page",
        "nitter_feed",
        "reddit_feed",
        "lobsters_feed",
        "mastodon_feed",
        "youtube_channel",
        "podcast_feed",
    }, f"unsupported DEFAULT_SOURCES kind: {source.slug}={source.kind}"
    fetched: list[str] = []

    def fetch_feed(url: str) -> bytes:
        fetched.append(url)
        return b"""<rss version="2.0"><channel><title>Test feed</title><item>
          <title>Test article</title><link>https://x.com/example/status/123</link>
          <description>Test body</description></item></channel></rss>"""

    def scrape_source(candidate: SourceDefinition) -> list[dict[str, Any]]:
        fetched.append(candidate.url)
        return [{"title": "Test article", "url": "https://example.test/article"}]

    monkeypatch.setattr("news_dashboard.ingest.service._fetch_feed_content", fetch_feed)
    monkeypatch.setattr("news_dashboard.scraper.scrape_source", scrape_source)

    entries = _fetch_entries_by_kind(source)

    assert len(fetched) == 1
    assert len(entries) == 1
    assert entries[0]["title"] == "Test article"
    if source.kind == "reddit_feed":
        assert fetched[0].endswith("/.rss")
    elif source.kind == "nitter_feed":
        assert fetched[0].endswith(f"/{source.url.rstrip('/').split('/')[-1]}/rss")
    else:
        assert fetched == [source.url]
