"""Regression tests for Hugging Face Blog ingest (issue #280).

The HF blog RSS feed provides no description/content — only title, date, and
link per entry.  Articles must still land with a non-empty summary by fetching
a snippet from the article page.  No live network calls are made.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import feedparser

import news_dashboard.body_fetch as body_fetch_module
import news_dashboard.ingest as ingest_module
from news_dashboard.db import connect
from news_dashboard.ingest import (
    _MAX_SNIPPET_FETCHES_PER_RUN,
    _SNIPPET_FETCH_SOURCES,
    ingest_all,
)
from news_dashboard.sources import SourceDefinition


class _ParsedFeed:
    bozo = False

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.entries = entries


def _hf_source() -> SourceDefinition:
    return SourceDefinition(
        "huggingface-blog",
        "Hugging Face Blog",
        "https://huggingface.co/blog/feed.xml",
        "ai-llm",
        "rss_feed",
        80,
    )


def _feed_entry(slug: str) -> dict[str, str]:
    """Minimal feed entry matching the real HF feed format — no summary field."""
    return {
        "link": f"https://huggingface.co/blog/{slug}",
        "title": f"HF Article: {slug}",
        "published": "Mon, 01 Jun 2026 00:00:00 GMT",
    }


# ── configuration ─────────────────────────────────────────────────────────────


def test_hf_blog_in_snippet_fetch_sources() -> None:
    assert "huggingface-blog" in _SNIPPET_FETCH_SOURCES


def test_snippet_fetch_cap_is_positive() -> None:
    assert _MAX_SNIPPET_FETCHES_PER_RUN > 0


# ── snippet enrichment ────────────────────────────────────────────────────────


def test_hf_blog_empty_description_triggers_snippet_fetch(tmp_path: Path, monkeypatch: Any) -> None:
    """New HF blog articles with no feed description should get a snippet from the page."""
    db_path = tmp_path / "hf_snippet.db"
    monkeypatch.setattr(ingest_module, "DEFAULT_SOURCES", [_hf_source()])

    monkeypatch.setattr(
        feedparser,
        "parse",
        lambda _url, **_kw: _ParsedFeed([_feed_entry("peft-beyond-lora")]),
    )

    snippet_text = (
        "Parameter-efficient fine-tuning lets you adapt large models with minimal compute."
    )
    monkeypatch.setattr(body_fetch_module, "extract_body", lambda _url: (snippet_text, "ok"))

    ingest_all(db_path)

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT summary FROM articles WHERE source_slug = 'huggingface-blog'"
        ).fetchone()

    assert row is not None
    assert snippet_text[:280] in row["summary"]


def test_hf_blog_non_empty_feed_description_skips_snippet_fetch(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """If the feed does provide a description, no extra HTTP request is made."""
    db_path = tmp_path / "hf_has_desc.db"
    monkeypatch.setattr(ingest_module, "DEFAULT_SOURCES", [_hf_source()])

    entry_with_desc = _feed_entry("some-article")
    entry_with_desc["summary"] = "Feed-provided description already here."

    monkeypatch.setattr(
        feedparser,
        "parse",
        lambda _url, **_kw: _ParsedFeed([entry_with_desc]),
    )

    fetch_calls: list[str] = []

    def _fail_if_called(url: str) -> tuple[str, str]:
        fetch_calls.append(url)
        return "", "error"

    monkeypatch.setattr(body_fetch_module, "extract_body", _fail_if_called)

    ingest_all(db_path)

    assert fetch_calls == [], "extract_body must not be called when feed description is present"

    with connect(db_path) as conn:
        row = conn.execute("SELECT summary FROM articles").fetchone()
    assert row is not None
    assert "Feed-provided description" in row["summary"]


def test_hf_blog_snippet_fetch_skipped_for_existing_articles(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Snippet fetch must not happen for articles already stored (repeat ingest run)."""
    db_path = tmp_path / "hf_repeat.db"
    monkeypatch.setattr(ingest_module, "DEFAULT_SOURCES", [_hf_source()])

    monkeypatch.setattr(
        feedparser,
        "parse",
        lambda _url, **_kw: _ParsedFeed([_feed_entry("repeat-article")]),
    )

    call_count = 0

    def _count_calls(url: str) -> tuple[str, str]:
        nonlocal call_count
        call_count += 1
        return "First-run snippet text for the article.", "ok"

    monkeypatch.setattr(body_fetch_module, "extract_body", _count_calls)

    # First run — snippet should be fetched once
    ingest_all(db_path)
    assert call_count == 1

    # Second run — same URL already in DB; no second fetch
    ingest_all(db_path)
    assert call_count == 1, "extract_body called again on repeat run — expected skip"


def test_hf_blog_snippet_fetch_capped_per_run(tmp_path: Path, monkeypatch: Any) -> None:
    """Snippet fetches must not exceed _MAX_SNIPPET_FETCHES_PER_RUN per ingest run."""
    db_path = tmp_path / "hf_cap.db"
    monkeypatch.setattr(ingest_module, "DEFAULT_SOURCES", [_hf_source()])

    # Produce more entries than the cap
    entries = [_feed_entry(f"article-{i}") for i in range(_MAX_SNIPPET_FETCHES_PER_RUN + 5)]
    monkeypatch.setattr(
        feedparser,
        "parse",
        lambda _url, **_kw: _ParsedFeed(entries),
    )

    fetch_calls: list[str] = []

    def _record_call(url: str) -> tuple[str, str]:
        fetch_calls.append(url)
        return f"Snippet for {url}", "ok"

    monkeypatch.setattr(body_fetch_module, "extract_body", _record_call)

    ingest_all(db_path)

    assert len(fetch_calls) <= _MAX_SNIPPET_FETCHES_PER_RUN


def test_hf_blog_snippet_fetch_failure_still_inserts_article(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A snippet fetch error must not prevent article insertion."""
    db_path = tmp_path / "hf_fail.db"
    monkeypatch.setattr(ingest_module, "DEFAULT_SOURCES", [_hf_source()])

    monkeypatch.setattr(
        feedparser,
        "parse",
        lambda _url, **_kw: _ParsedFeed([_feed_entry("failed-snippet")]),
    )

    monkeypatch.setattr(body_fetch_module, "extract_body", lambda _url: ("", "error"))

    result = ingest_all(db_path)

    assert result.results.get("huggingface-blog", -1) == 1

    with connect(db_path) as conn:
        row = conn.execute("SELECT summary, title FROM articles").fetchone()
    assert row is not None
    assert row["title"] == "HF Article: failed-snippet"
    assert row["summary"] == ""


def test_other_sources_not_affected_by_snippet_fetch(tmp_path: Path, monkeypatch: Any) -> None:
    """Snippet fetch must not be triggered for sources not in _SNIPPET_FETCH_SOURCES."""
    db_path = tmp_path / "other_source.db"
    other = SourceDefinition(
        "openai-blog", "OpenAI Blog", "https://openai.com/news/rss.xml", "ai-llm", "rss_feed", 85
    )
    monkeypatch.setattr(ingest_module, "DEFAULT_SOURCES", [other])

    monkeypatch.setattr(
        feedparser,
        "parse",
        lambda _url, **_kw: _ParsedFeed(
            [{"link": "https://openai.com/blog/gpt-5", "title": "GPT-5"}]
        ),
    )

    fetch_calls: list[str] = []

    def _fail_if_called(url: str) -> tuple[str, str]:
        fetch_calls.append(url)
        return "", "error"

    monkeypatch.setattr(body_fetch_module, "extract_body", _fail_if_called)

    ingest_all(db_path)

    assert fetch_calls == [], "extract_body must not be called for non-HF sources"
