"""Pure rendering tests for daily briefing email templates."""

from __future__ import annotations

from datetime import date
from typing import Any

from news_dashboard.briefing_email.rendering import render_briefing_email


def _briefing(*, body: str = "First story body.") -> dict[str, Any]:
    return {
        "title": "Today's <Briefing>",
        "summary": "The executive summary explains what matters.",
        "content": {
            "sections": [
                {"title": "First section", "body": body, "citations": [2]},
                {"title": "Second section", "body": "Second story body.", "citations": [1]},
            ]
        },
        "articles": [
            {"id": 1, "title": "Second source", "url": "javascript:alert(1)", "source_name": "B"},
            {
                "id": 2,
                "title": "First source",
                "url": "https://example.com/first",
                "source_name": "A",
            },
        ],
    }


def _urls() -> dict[str, Any]:
    return {
        "local_date": date(2026, 7, 17),
        "timezone_name": "Europe/Bucharest",
        "briefing_url": "https://news.example/briefings/7",
        "preferences_url": "https://news.example/settings/notifications",
        "unsubscribe_url": "https://news.example/unsubscribe/token",
    }


def test_rendering_escapes_generated_html() -> None:
    rendered = render_briefing_email(_briefing(body="<script>alert(1)</script>"), **_urls())
    assert "<script>" not in rendered.html_body
    assert "&lt;script&gt;" in rendered.html_body
    assert "Today&#39;s &lt;Briefing&gt;" in rendered.html_body


def test_plain_text_preserves_literal_generated_characters() -> None:
    rendered = render_briefing_email(_briefing(body="What's <important> today"), **_urls())
    assert "What's <important> today" in rendered.text_body
    assert "Today&#39;s &lt;Briefing&gt;" not in rendered.text_body
    assert "Today's <Briefing>" in rendered.text_body


def test_rendering_suppresses_unsafe_links_without_reordering_stories() -> None:
    rendered = render_briefing_email(_briefing(), **_urls())
    assert "javascript:" not in rendered.html_body
    assert "javascript:" not in rendered.text_body
    assert rendered.text_body.index("First section") < rendered.text_body.index("Second section")
    assert rendered.text_body.index("First source") < rendered.text_body.index("Second source")


def test_rendering_includes_summary_reading_time_and_footer_links() -> None:
    briefing = _briefing(body=" ".join(["word"] * 400))
    rendered = render_briefing_email(briefing, **_urls())
    assert rendered.estimated_minutes == 3
    assert "The executive summary explains what matters." in rendered.text_body
    assert "3 min read" in rendered.text_body
    assert "Europe/Bucharest" in rendered.text_body
    assert "https://news.example/briefings/7" in rendered.text_body
    assert "https://news.example/settings/notifications" in rendered.text_body
    assert "https://news.example/unsubscribe/token" in rendered.text_body


def test_rendering_suppresses_unsafe_footer_links() -> None:
    urls = _urls()
    urls["preferences_url"] = "javascript:alert(1)"
    rendered = render_briefing_email(_briefing(), **urls)
    assert "javascript:" not in rendered.html_body
    assert "javascript:" not in rendered.text_body


def test_rendering_suppresses_malformed_links() -> None:
    urls = _urls()
    urls["briefing_url"] = "https://[invalid"
    rendered = render_briefing_email(_briefing(), **urls)
    assert "https://[invalid" not in rendered.html_body
    assert "https://[invalid" not in rendered.text_body


def test_rendering_suppresses_links_with_malformed_ports() -> None:
    urls = _urls()
    urls["briefing_url"] = "https://example.com:bad/a"
    rendered = render_briefing_email(_briefing(), **urls)
    assert "https://example.com:bad/a" not in rendered.html_body
    assert "https://example.com:bad/a" not in rendered.text_body
