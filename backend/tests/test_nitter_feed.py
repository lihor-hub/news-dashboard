"""Tests for Nitter RSS feed fetching — no live network calls."""

from __future__ import annotations

import feedparser
import pytest

from news_dashboard.ingest import (
    _NITTER_INSTANCES,
    FeedFetchError,
    _fetch_nitter_feed,
    _nitter_handle,
)
from news_dashboard.sources import DEFAULT_SOURCES, SourceDefinition

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_source(handle: str) -> SourceDefinition:
    return SourceDefinition(
        f"x-{handle.lower()}",
        f"@{handle} on X",
        f"https://x.com/{handle}",
        "ai-social",
        "nitter_feed",
        60,
    )


def _mock_ok(entries: list[dict[str, str]]) -> feedparser.FeedParserDict:
    result = feedparser.FeedParserDict()
    result["entries"] = [feedparser.FeedParserDict(e) for e in entries]
    result["bozo"] = False
    return result


def _mock_fail() -> feedparser.FeedParserDict:
    result = feedparser.FeedParserDict()
    result["entries"] = []
    result["bozo"] = True
    result["bozo_exception"] = ConnectionError("refused")
    return result


# ── handle extraction ─────────────────────────────────────────────────────────


def test_nitter_handle_plain_url() -> None:
    assert _nitter_handle("https://x.com/AnthropicAI") == "AnthropicAI"


def test_nitter_handle_trailing_slash() -> None:
    assert _nitter_handle("https://x.com/sama/") == "sama"


def test_nitter_handle_twitter_dot_com() -> None:
    assert _nitter_handle("https://twitter.com/ylecun") == "ylecun"


def test_nitter_handle_mixed_case_preserved() -> None:
    assert _nitter_handle("https://x.com/ClementDelangue") == "ClementDelangue"


# ── successful fetch ──────────────────────────────────────────────────────────


def test_fetch_nitter_succeeds_on_first_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_parse(url: str, **_kwargs: object) -> feedparser.FeedParserDict:
        calls.append(url)
        return _mock_ok([{"link": "https://x.com/AnthropicAI/status/1", "title": "Hello AI"}])

    monkeypatch.setattr("news_dashboard.ingest.feedparser.parse", fake_parse)
    entries = _fetch_nitter_feed(_make_source("AnthropicAI"))

    assert len(entries) == 1
    assert entries[0]["title"] == "Hello AI"
    assert entries[0]["url"] == "https://x.com/AnthropicAI/status/1"
    # Only one network call — no unnecessary fallback
    assert len(calls) == 1
    assert f"{_NITTER_INSTANCES[0]}/AnthropicAI/rss" in calls[0]


def test_fetch_nitter_normalises_missing_title(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_parse(_url: str, **_kwargs: object) -> feedparser.FeedParserDict:
        return _mock_ok([{"link": "https://x.com/sama/status/2"}])

    monkeypatch.setattr("news_dashboard.ingest.feedparser.parse", fake_parse)
    entries = _fetch_nitter_feed(_make_source("sama"))
    assert entries[0]["title"] == "Untitled"


# ── fallback behaviour ────────────────────────────────────────────────────────


def test_fetch_nitter_falls_back_on_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_parse(url: str, **_kwargs: object) -> feedparser.FeedParserDict:
        calls.append(url)
        if _NITTER_INSTANCES[0] in url:
            return _mock_fail()
        return _mock_ok([{"link": "https://x.com/karpathy/status/3", "title": "Post"}])

    monkeypatch.setattr("news_dashboard.ingest.feedparser.parse", fake_parse)
    entries = _fetch_nitter_feed(_make_source("karpathy"))

    assert len(entries) == 1
    # First instance tried, then second succeeded
    assert len(calls) == 2
    assert _NITTER_INSTANCES[0] in calls[0]
    assert _NITTER_INSTANCES[1] in calls[1]


def test_fetch_nitter_raises_when_all_instances_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_parse(_url: str, **_kwargs: object) -> feedparser.FeedParserDict:
        return _mock_fail()

    monkeypatch.setattr("news_dashboard.ingest.feedparser.parse", fake_parse)
    with pytest.raises(FeedFetchError, match="All Nitter instances failed for @ylecun"):
        _fetch_nitter_feed(_make_source("ylecun"))


def test_fetch_nitter_tries_all_instances_before_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_parse(url: str, **_kwargs: object) -> feedparser.FeedParserDict:
        calls.append(url)
        return _mock_fail()

    monkeypatch.setattr("news_dashboard.ingest.feedparser.parse", fake_parse)
    with pytest.raises(FeedFetchError):
        _fetch_nitter_feed(_make_source("gdb"))
    assert len(calls) == len(_NITTER_INSTANCES)


# ── instance list invariants ──────────────────────────────────────────────────


def test_nitter_instances_has_at_least_two() -> None:
    assert len(_NITTER_INSTANCES) >= 2, "need at least 2 instances for meaningful fallback"


def test_nitter_instances_are_unique() -> None:
    assert len(_NITTER_INSTANCES) == len(set(_NITTER_INSTANCES))


# ── DEFAULT_SOURCES sanity checks ─────────────────────────────────────────────


_NITTER_SOURCES = [s for s in DEFAULT_SOURCES if s.kind == "nitter_feed"]
_EXPECTED_HANDLES = {
    "AnthropicAI",
    "OpenAI",
    "GoogleDeepMind",
    "AIatMeta",
    "MistralAI",
    "huggingface",
    "xai",
    "DarioAmodei",
    "jackclarksf",
    "sama",
    "gdb",
    "demishassabis",
    "ylecun",
    "arthurmensch",
    "karpathy",
    "ClementDelangue",
    "theo",
}


def test_nitter_sources_count() -> None:
    assert len(_NITTER_SOURCES) == 17


def test_nitter_sources_all_have_correct_kind() -> None:
    for s in _NITTER_SOURCES:
        assert s.kind == "nitter_feed", f"{s.slug} has wrong kind"


def test_nitter_sources_urls_are_x_dot_com() -> None:
    for s in _NITTER_SOURCES:
        assert s.url.startswith("https://x.com/"), f"{s.slug} URL unexpected: {s.url}"


def test_nitter_sources_handles_match_expected() -> None:
    actual = {_nitter_handle(s.url) for s in _NITTER_SOURCES}
    assert actual == _EXPECTED_HANDLES


def test_nitter_sources_slugs_unique() -> None:
    slugs = [s.slug for s in _NITTER_SOURCES]
    assert len(slugs) == len(set(slugs))


def test_nitter_sources_all_ai_social_category() -> None:
    for s in _NITTER_SOURCES:
        assert s.category == "ai-social", f"{s.slug} has category {s.category!r}"
