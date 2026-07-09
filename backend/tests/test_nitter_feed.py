"""Tests for Nitter RSS feed fetching — no live network calls."""

from __future__ import annotations

import urllib.error
from http.client import HTTPMessage
from typing import ClassVar

import pytest

from news_dashboard.ingest import (
    _FEED_AGENT,
    _NITTER_INSTANCES,
    FEED_FETCH_MAX_BYTES,
    FEED_FETCH_MAX_RETRIES,
    FEED_FETCH_TIMEOUT_SECS,
    FeedFetchError,
    _fetch_feed_content,
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


def _ok_entries(entries: list[dict[str, str]]) -> list[dict[str, object]]:
    return [
        {
            "url": e.get("link", ""),
            "title": e.get("title") or "Untitled",
            "description": "",
            "date": None,
        }
        for e in entries
    ]


# ── handle extraction ─────────────────────────────────────────────────────────


def test_nitter_handle_plain_url() -> None:
    assert _nitter_handle("https://x.com/AnthropicAI") == "AnthropicAI"


def test_nitter_handle_trailing_slash() -> None:
    assert _nitter_handle("https://x.com/sama/") == "sama"


def test_nitter_handle_twitter_dot_com() -> None:
    assert _nitter_handle("https://twitter.com/ylecun") == "ylecun"


def test_nitter_handle_mixed_case_preserved() -> None:
    assert _nitter_handle("https://x.com/ClementDelangue") == "ClementDelangue"


# ── _fetch_feed_content ───────────────────────────────────────────────────────


def test_fetch_feed_content_rejects_non_http(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(FeedFetchError, match="non-HTTP"):
        _fetch_feed_content("ftp://example.com/feed.xml")


def test_fetch_feed_content_rejects_file_url(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(FeedFetchError, match="non-HTTP"):
        _fetch_feed_content("file:///etc/passwd")


def test_fetch_feed_content_rejects_private_network_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_open(_req: object, *, timeout: float) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("news_dashboard.ingest.open_server_fetch_url", fake_open)

    with pytest.raises(FeedFetchError, match="unsafe host"):
        _fetch_feed_content("http://127.0.0.1/feed.xml")

    assert called is False


def test_fetch_feed_content_sends_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str | None] = []

    class _FakeResp:
        headers: ClassVar[dict[str, str]] = {}

        def read(self, _n: int = -1) -> bytes:
            return b"<rss/>"

        def __enter__(self) -> _FakeResp:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def fake_open(req: object, *, timeout: float) -> _FakeResp:
        import urllib.request as ur

        assert isinstance(req, ur.Request)
        captured.append(req.get_header("User-agent"))
        assert timeout == FEED_FETCH_TIMEOUT_SECS
        return _FakeResp()

    monkeypatch.setattr("news_dashboard.ingest.open_server_fetch_url", fake_open)
    _fetch_feed_content("https://example.com/feed.xml")
    assert captured == [_FEED_AGENT]


def test_fetch_feed_content_converts_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(_req: object, *, timeout: float) -> None:
        msg = "timed out"
        raise TimeoutError(msg)

    monkeypatch.setattr("news_dashboard.ingest.open_server_fetch_url", fake_open)
    with pytest.raises(FeedFetchError, match="timed out"):
        _fetch_feed_content("https://example.com/feed.xml")


def test_fetch_feed_content_converts_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(_req: object, *, timeout: float) -> None:
        msg = "Name or service not known"
        raise urllib.error.URLError(msg)

    monkeypatch.setattr("news_dashboard.ingest.open_server_fetch_url", fake_open)
    with pytest.raises(FeedFetchError, match="network error"):
        _fetch_feed_content("https://example.com/feed.xml")


# ── 429/503 retry ─────────────────────────────────────────────────────────────


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = HTTPMessage()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://example.com/feed.xml", code, "err", headers, None)


def test_fetch_feed_content_retries_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"<rss>ok</rss>"
    attempts = {"n": 0}

    def fake_open(_req: object, *, timeout: float) -> _SizedFakeResp:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(429)
        return _SizedFakeResp(body)

    sleeps: list[float] = []
    monkeypatch.setattr("news_dashboard.ingest.open_server_fetch_url", fake_open)
    monkeypatch.setattr("news_dashboard.ingest.time.sleep", sleeps.append)

    assert _fetch_feed_content("https://example.com/feed.xml") == body
    assert attempts["n"] == 2
    assert sleeps, "expected a backoff sleep between attempts"


def test_fetch_feed_content_gives_up_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"n": 0}

    def fake_open(_req: object, *, timeout: float) -> None:
        attempts["n"] += 1
        raise _http_error(429)

    monkeypatch.setattr("news_dashboard.ingest.open_server_fetch_url", fake_open)
    monkeypatch.setattr("news_dashboard.ingest.time.sleep", lambda _s: None)

    with pytest.raises(FeedFetchError, match="network error"):
        _fetch_feed_content("https://example.com/feed.xml")
    assert attempts["n"] == FEED_FETCH_MAX_RETRIES + 1


def test_fetch_feed_content_honors_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"n": 0}

    def fake_open(_req: object, *, timeout: float) -> _SizedFakeResp:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(429, retry_after="7")
        return _SizedFakeResp(b"<rss/>")

    sleeps: list[float] = []
    monkeypatch.setattr("news_dashboard.ingest.open_server_fetch_url", fake_open)
    monkeypatch.setattr("news_dashboard.ingest.time.sleep", sleeps.append)

    _fetch_feed_content("https://example.com/feed.xml")
    assert sleeps == [7.0]


def test_fetch_feed_content_does_not_retry_404(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"n": 0}

    def fake_open(_req: object, *, timeout: float) -> None:
        attempts["n"] += 1
        raise _http_error(404)

    monkeypatch.setattr("news_dashboard.ingest.open_server_fetch_url", fake_open)
    monkeypatch.setattr("news_dashboard.ingest.time.sleep", lambda _s: None)

    with pytest.raises(FeedFetchError, match="network error"):
        _fetch_feed_content("https://example.com/feed.xml")
    assert attempts["n"] == 1


# ── size cap ──────────────────────────────────────────────────────────────────


class _SizedFakeResp:
    def __init__(self, body: bytes, *, content_length: str | None = None) -> None:
        self._body = body
        self.headers = {"Content-Length": content_length} if content_length else {}

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            return self._body
        return self._body[:n]

    def __enter__(self) -> _SizedFakeResp:
        return self

    def __exit__(self, *_: object) -> None:
        pass


def test_fetch_feed_content_under_limit_parses_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b"<rss>" + b"x" * 100 + b"</rss>"
    monkeypatch.setattr(
        "news_dashboard.ingest.open_server_fetch_url",
        lambda *_a, **_k: _SizedFakeResp(body),
    )
    assert _fetch_feed_content("https://example.com/feed.xml") == body


def test_fetch_feed_content_rejects_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b"x" * (FEED_FETCH_MAX_BYTES + 1)
    monkeypatch.setattr(
        "news_dashboard.ingest.open_server_fetch_url",
        lambda *_a, **_k: _SizedFakeResp(body),
    )
    with pytest.raises(FeedFetchError, match="exceeded"):
        _fetch_feed_content("https://example.com/feed.xml")


def test_fetch_feed_content_rejects_oversized_content_length_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    class _NeverReadResp(_SizedFakeResp):
        def read(self, n: int = -1) -> bytes:
            nonlocal called
            called = True
            return super().read(n)

    resp = _NeverReadResp(b"short body", content_length=str(FEED_FETCH_MAX_BYTES + 1))
    monkeypatch.setattr("news_dashboard.ingest.open_server_fetch_url", lambda *_a, **_k: resp)
    with pytest.raises(FeedFetchError, match="too large"):
        _fetch_feed_content("https://example.com/feed.xml")
    assert called is False


def test_fetch_feed_content_ignores_invalid_content_length_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b"<rss/>"
    resp = _SizedFakeResp(body, content_length="not-a-number")
    monkeypatch.setattr("news_dashboard.ingest.open_server_fetch_url", lambda *_a, **_k: resp)
    assert _fetch_feed_content("https://example.com/feed.xml") == body


# ── successful fetch ──────────────────────────────────────────────────────────


def test_fetch_nitter_succeeds_on_first_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_parse_url(url: str) -> list[dict[str, object]]:
        calls.append(url)
        return _ok_entries([{"link": "https://x.com/AnthropicAI/status/1", "title": "Hello AI"}])

    monkeypatch.setattr("news_dashboard.ingest._parse_feed_url", fake_parse_url)
    entries = _fetch_nitter_feed(_make_source("AnthropicAI"))

    assert len(entries) == 1
    assert entries[0]["title"] == "Hello AI"
    assert entries[0]["url"] == "https://x.com/AnthropicAI/status/1"
    # Only one network call — no unnecessary fallback
    assert len(calls) == 1
    assert f"{_NITTER_INSTANCES[0]}/AnthropicAI/rss" in calls[0]


def test_fetch_nitter_normalises_missing_title(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_parse_url(_url: str) -> list[dict[str, object]]:
        return _ok_entries([{"link": "https://x.com/sama/status/2"}])

    monkeypatch.setattr("news_dashboard.ingest._parse_feed_url", fake_parse_url)
    entries = _fetch_nitter_feed(_make_source("sama"))
    assert entries[0]["title"] == "Untitled"


# ── fallback behaviour ────────────────────────────────────────────────────────


def test_fetch_nitter_falls_back_on_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_parse_url(url: str) -> list[dict[str, object]]:
        calls.append(url)
        if _NITTER_INSTANCES[0] in url:
            msg = "refused"
            raise FeedFetchError(msg)
        return _ok_entries([{"link": "https://x.com/karpathy/status/3", "title": "Post"}])

    monkeypatch.setattr("news_dashboard.ingest._parse_feed_url", fake_parse_url)
    entries = _fetch_nitter_feed(_make_source("karpathy"))

    assert len(entries) == 1
    # First instance tried, then second succeeded
    assert len(calls) == 2
    assert _NITTER_INSTANCES[0] in calls[0]
    assert _NITTER_INSTANCES[1] in calls[1]


def test_fetch_nitter_falls_back_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_parse_url(url: str) -> list[dict[str, object]]:
        calls.append(url)
        if _NITTER_INSTANCES[0] in url:
            msg = f"Feed fetch timed out after {FEED_FETCH_TIMEOUT_SECS}s: {url}"
            raise FeedFetchError(msg)
        return _ok_entries([{"link": "https://x.com/gdb/status/1", "title": "Timeout test"}])

    monkeypatch.setattr("news_dashboard.ingest._parse_feed_url", fake_parse_url)
    entries = _fetch_nitter_feed(_make_source("gdb"))

    assert len(entries) == 1
    assert len(calls) == 2


def test_fetch_nitter_raises_when_all_instances_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_parse_url(_url: str) -> list[dict[str, object]]:
        msg = "refused"
        raise FeedFetchError(msg)

    monkeypatch.setattr("news_dashboard.ingest._parse_feed_url", fake_parse_url)
    with pytest.raises(FeedFetchError, match="All Nitter instances failed for @ylecun"):
        _fetch_nitter_feed(_make_source("ylecun"))


def test_fetch_nitter_skips_placeholder_without_status_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 'not whitelisted' placeholder (no /status/ links) is treated as a failure."""
    calls: list[str] = []

    def fake_parse_url(url: str) -> list[dict[str, object]]:
        calls.append(url)
        if _NITTER_INSTANCES[0] in url:
            # xcancel-style placeholder: one item linking back to the RSS URL.
            return _ok_entries(
                [{"link": "https://rss.xcancel.com/xai/rss", "title": "Not whitelisted!"}]
            )
        return _ok_entries([{"link": "https://x.com/xai/status/9", "title": "Real tweet"}])

    monkeypatch.setattr("news_dashboard.ingest._parse_feed_url", fake_parse_url)
    entries = _fetch_nitter_feed(_make_source("xai"))

    assert len(calls) == 2, "should skip the placeholder instance and try the next"
    assert [e["title"] for e in entries] == ["Real tweet"]


def test_fetch_nitter_raises_when_only_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_parse_url(url: str) -> list[dict[str, object]]:
        return _ok_entries([{"link": url, "title": "RSS reader not yet whitelisted!"}])

    monkeypatch.setattr("news_dashboard.ingest._parse_feed_url", fake_parse_url)
    with pytest.raises(FeedFetchError, match="All Nitter instances failed for @xai"):
        _fetch_nitter_feed(_make_source("xai"))


def test_fetch_nitter_tries_all_instances_before_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_parse_url(url: str) -> list[dict[str, object]]:
        calls.append(url)
        msg = "refused"
        raise FeedFetchError(msg)

    monkeypatch.setattr("news_dashboard.ingest._parse_feed_url", fake_parse_url)
    with pytest.raises(FeedFetchError):
        _fetch_nitter_feed(_make_source("gdb"))
    assert len(calls) == len(_NITTER_INSTANCES)


# ── instance list invariants ──────────────────────────────────────────────────


def test_nitter_instances_has_at_least_two() -> None:
    assert len(_NITTER_INSTANCES) >= 2, "need at least 2 instances for meaningful fallback"


def test_nitter_instances_are_unique() -> None:
    assert len(_NITTER_INSTANCES) == len(set(_NITTER_INSTANCES))


def test_nitter_instances_include_working_xcancel() -> None:
    """xcancel.com is the currently-reachable instance and should be tried first."""
    assert _NITTER_INSTANCES[0] == "xcancel.com"


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
