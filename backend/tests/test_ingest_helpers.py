"""Unit tests for pure ingest helpers — no DB or network required."""

from __future__ import annotations

import pytest

from news_dashboard.ingest.service import (
    canonicalize_url,
    clean_html,
    infer_tags,
    make_reason,
    make_summary,
    parse_date,
)
from news_dashboard.sources.service import SourceDefinition


def _src(
    *,
    slug: str = "acme",
    name: str = "Acme",
    category: str = "ai-llm",
    kind: str = "rss_feed",
    priority: int = 50,
) -> SourceDefinition:
    return SourceDefinition(
        slug=slug,
        name=name,
        url="https://acme.test/feed",
        category=category,
        kind=kind,
        priority=priority,
    )


# ── clean_html ────────────────────────────────────────────────────────────────


def test_clean_html_empty() -> None:
    assert clean_html(None) == ""
    assert clean_html("") == ""


def test_clean_html_strips_tags_and_entities() -> None:
    assert clean_html("<p>Hello&amp;  <b>world</b></p>") == "Hello& world"


# ── canonicalize_url ──────────────────────────────────────────────────────────


def test_canonicalize_url_strips_tracking_and_fragment() -> None:
    out = canonicalize_url("https://x.test/p?utm_source=rss&id=5#frag")
    assert "utm_source" not in out
    assert "id=5" in out
    assert "#frag" not in out


def test_canonicalize_url_normalizes_scheme_and_host_case() -> None:
    assert canonicalize_url("HTTP://X.test/p") == canonicalize_url("http://x.test/p")


def test_canonicalize_url_strips_trailing_slash() -> None:
    assert canonicalize_url("https://x.test/p/") == canonicalize_url("https://x.test/p")


def test_canonicalize_url_keeps_root_slash() -> None:
    assert canonicalize_url("https://x.test/") == "https://x.test/"


def test_canonicalize_url_sorts_query_params() -> None:
    assert canonicalize_url("https://x.test/p?b=2&a=1") == canonicalize_url(
        "https://x.test/p?a=1&b=2"
    )


def test_canonicalize_url_strips_additional_tracking_params() -> None:
    out = canonicalize_url(
        "https://x.test/p?id=5&mc_cid=abc&mc_eid=def&igshid=ghi&ck_subscriber_id=jkl"
    )
    assert out == canonicalize_url("https://x.test/p?id=5")


# ── parse_date ────────────────────────────────────────────────────────────────


def test_parse_date_rfc822() -> None:
    out = parse_date({"published": "Mon, 01 Jun 2026 12:00:00 +0000"})
    assert out is not None
    assert out.startswith("2026-06-01T12:00:00")


def test_parse_date_unparseable_returns_raw() -> None:
    assert parse_date({"published": "not a date"}) == "not a date"


def test_parse_date_none_when_absent() -> None:
    assert parse_date({"published": None, "updated": None, "created": None}) is None


# ── infer_tags ────────────────────────────────────────────────────────────────


def test_infer_tags_detects_keywords() -> None:
    tags = infer_tags("A new LLM agent framework in Python")
    assert "llm" in tags or "agents" in tags
    assert "python" in tags


def test_infer_tags_empty_for_unrelated_text() -> None:
    assert infer_tags("the quick brown fox") == []


# ── make_reason (first-match-wins rule chain) ────────────────────────────────


def test_make_reason_release_with_version() -> None:
    out = make_reason("Foo v1.2.3 released", _src(kind="github_release_feed"), [])
    assert "1.2.3" in out
    assert "New release" in out


def test_make_reason_release_without_version() -> None:
    out = make_reason("Foo released", _src(kind="github_release_feed"), [])
    assert out == "New release from Acme."


def test_make_reason_security() -> None:
    assert "Security update" in make_reason("x", _src(), ["security"])


def test_make_reason_tutorial() -> None:
    out = make_reason("x", _src(category="ai-llm"), ["tutorial"])
    assert "How-to" in out
    assert "ai/llm" in out


def test_make_reason_trending_hacker_news() -> None:
    out = make_reason("x", _src(slug="hacker-news", kind="trending_feed"), [])
    assert out == "Trending on Hacker News."


def test_make_reason_trending_github() -> None:
    out = make_reason("x", _src(slug="github-trending-python", kind="trending_feed"), [])
    assert "Trending Python repository" in out


def test_make_reason_trending_generic() -> None:
    out = make_reason("x", _src(slug="other-feed", kind="trending_feed"), [])
    assert out == "Trending item from Acme."


def test_make_reason_llm_then_python_then_infra() -> None:
    assert "AI/agent" in make_reason("x", _src(), ["llm"])
    assert "Python ecosystem" in make_reason("x", _src(), ["python"])
    assert "Cloud/infrastructure" in make_reason("x", _src(), ["infra"])


def test_make_reason_fallback() -> None:
    out = make_reason("x", _src(category="dev-tools"), [])
    assert out == "Dev Tools — Acme."


# ── make_summary ──────────────────────────────────────────────────────────────


def test_make_summary_truncates_and_scores() -> None:
    long = "word " * 100
    summary, reason, score, tags = make_summary("Python release", long, _src(priority=50))
    assert summary.endswith("…")
    assert len(summary) <= 281
    assert score == 60  # priority 50 + 10 for having tags
    assert "python" in tags
    assert reason


def test_make_summary_no_tags_no_bonus() -> None:
    _, _, score, tags = make_summary("zzz", "nothing here", _src(priority=20, category="misc"))
    assert score == 20
    assert tags == ""


@pytest.mark.parametrize("priority", [95, 100, 120])
def test_make_summary_score_capped_at_100(priority: int) -> None:
    _, _, score, _ = make_summary("Python", "llm agent", _src(priority=priority))
    assert score == 100
