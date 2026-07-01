"""Tests for new feed types: Reddit, Lobsters, Mastodon."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from news_dashboard.ingest import (
    FeedFetchError,
    _fetch_lobsters_feed,
    _fetch_mastodon_feed,
    _fetch_reddit_feed,
    _ingest_source,
)
from news_dashboard.sources import SourceDefinition


def _make_source(kind: str, url: str, slug: str = "test") -> SourceDefinition:
    """Create a test source definition."""
    return SourceDefinition(
        slug=slug,
        name=f"Test {slug}",
        url=url,
        category="test",
        kind=kind,
        priority=50,
    )


def test_fetch_reddit_feed_converts_url() -> None:
    """Test that Reddit URL is converted to RSS format."""
    # Test URL without trailing slash
    source = _make_source("reddit_feed", "https://www.reddit.com/r/python")
    with patch("news_dashboard.ingest._parse_feed_url") as mock_parse:
        mock_parse.return_value = [{"url": "test", "title": "Test", "description": ""}]
        _fetch_reddit_feed(source)
        mock_parse.assert_called_once_with("https://www.reddit.com/r/python/.rss")

    # Test URL with trailing slash
    source = _make_source("reddit_feed", "https://www.reddit.com/r/python/")
    with patch("news_dashboard.ingest._parse_feed_url") as mock_parse:
        mock_parse.return_value = [{"url": "test", "title": "Test", "description": ""}]
        _fetch_reddit_feed(source)
        mock_parse.assert_called_once_with("https://www.reddit.com/r/python/.rss")


def test_fetch_lobsters_feed_passthrough() -> None:
    """Test that Lobsters URL is passed through unchanged."""
    source = _make_source("lobsters_feed", "https://lobste.rs/rss")
    with patch("news_dashboard.ingest._parse_feed_url") as mock_parse:
        mock_parse.return_value = [{"url": "test", "title": "Test", "description": ""}]
        _fetch_lobsters_feed(source)
        mock_parse.assert_called_once_with("https://lobste.rs/rss")


def test_fetch_mastodon_feed_passthrough() -> None:
    """Test that Mastodon URL is passed through unchanged."""
    source = _make_source("mastodon_feed", "https://mastodon.social/tags/tech.rss")
    with patch("news_dashboard.ingest._parse_feed_url") as mock_parse:
        mock_parse.return_value = [{"url": "test", "title": "Test", "description": ""}]
        _fetch_mastodon_feed(source)
        mock_parse.assert_called_once_with("https://mastodon.social/tags/tech.rss")


def test_ingest_source_routes_to_correct_function() -> None:
    """Test that _ingest_source routes to the correct fetch function based on kind."""
    # Test reddit_feed routing
    reddit_source = _make_source("reddit_feed", "https://www.reddit.com/r/test")
    with patch("news_dashboard.ingest._fetch_reddit_feed") as mock_reddit:
        mock_reddit.return_value = []
        with patch("news_dashboard.ingest.connect"):
            _ingest_source(reddit_source)
        mock_reddit.assert_called_once()

    # Test lobsters_feed routing
    lobsters_source = _make_source("lobsters_feed", "https://lobste.rs/rss")
    with patch("news_dashboard.ingest._fetch_lobsters_feed") as mock_lobsters:
        mock_lobsters.return_value = []
        with patch("news_dashboard.ingest.connect"):
            _ingest_source(lobsters_source)
        mock_lobsters.assert_called_once()

    # Test mastodon_feed routing
    mastodon_source = _make_source("mastodon_feed", "https://mastodon.social/tags/test.rss")
    with patch("news_dashboard.ingest._fetch_mastodon_feed") as mock_mastodon:
        mock_mastodon.return_value = []
        with patch("news_dashboard.ingest.connect"):
            _ingest_source(mastodon_source)
        mock_mastodon.assert_called_once()


def test_ingest_source_handles_fetch_errors() -> None:
    """Test that feed fetch errors are handled properly."""
    source = _make_source("reddit_feed", "https://www.reddit.com/r/nonexistent")
    with patch("news_dashboard.ingest._fetch_reddit_feed") as mock_fetch:
        mock_fetch.side_effect = FeedFetchError("Not found")
        with patch("news_dashboard.ingest.connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            result = _ingest_source(source)
            assert result.articles_found == 0
            assert result.articles_new == 0
            assert result.error_message == "Not found"
            # Verify error was recorded
            mock_conn.execute.assert_called()
            call_args = mock_conn.execute.call_args[0]
            assert "UPDATE sources SET" in call_args[0]
            assert "last_error=%s" in call_args[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
