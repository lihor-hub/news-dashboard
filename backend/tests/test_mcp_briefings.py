from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from news_dashboard.mcp.briefings import (
    MCP_STRUCTURED_CONTENT_BYTES,
    BriefingGetResult,
    BriefingListResult,
    build_briefing_get_result,
    build_briefing_list_result,
)
from news_dashboard.mcp.models import BriefingId, BriefingLimit, BriefingOffset


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 7,
        "title": "Morning briefing",
        "summary": "The important news.",
        "scope": "day",
        "since_at": datetime(2026, 8, 3, tzinfo=timezone.utc),
        "until_at": datetime(2026, 8, 4, tzinfo=timezone.utc),
        "created_at": datetime(2026, 8, 4, 8, tzinfo=timezone.utc),
        "content": {
            "sections": [{"title": "Top", "body": "Details", "citations": [11]}],
            "worth_opening": [11],
        },
        "articles": [
            {
                "id": 11,
                "title": "Article",
                "source_name": "Source",
                "url": "https://Example.com/story/?utm_source=x#fragment",
                "canonical_url": "https://Example.com/canonical/?utm_source=x#fragment",
                "section_index": 0,
                "citation_index": 0,
            }
        ],
        "user_id": 99,
        "status": "complete",
        "model": "secret-model",
        "error": "private error",
        "focus_prompt": "private prompt",
        "script": [{"speaker": "private"}],
        "trace_id": "private-trace",
    }
    row.update(overrides)
    return row


def _size(value: BriefingGetResult | BriefingListResult) -> int:
    return len(
        json.dumps(
            value.model_dump(mode="json"),
            default=str,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode()
    )


def test_build_get_uses_exact_public_allowlist_and_aware_serializable_datetimes() -> None:
    result = build_briefing_get_result(_row())

    payload = result.model_dump(mode="json")
    assert set(payload) == {"briefing", "truncated"}
    assert set(payload["briefing"]) == {
        "id",
        "title",
        "summary",
        "scope",
        "since_at",
        "until_at",
        "created_at",
        "content",
        "citations",
        "content_truncated",
        "omitted_sections",
        "omitted_citations",
    }
    assert set(payload["briefing"]["content"]) == {"sections", "worth_opening"}
    assert set(payload["briefing"]["content"]["sections"][0]) == {
        "title",
        "body",
        "citations",
    }
    assert set(payload["briefing"]["citations"][0]) == {
        "article_id",
        "title",
        "source",
        "url",
        "section_index",
        "citation_index",
    }
    assert result.briefing.created_at.tzinfo is not None
    assert result.briefing.since_at is not None
    assert result.briefing.since_at.tzinfo is not None
    assert json.dumps(payload)
    assert not ({"user_id", "status", "model", "error", "focus_prompt", "script"} & payload.keys())


def test_build_get_prefers_and_normalizes_canonical_url_then_falls_back() -> None:
    canonical = build_briefing_get_result(_row())
    fallback = build_briefing_get_result(
        _row(articles=[{**_row()["articles"][0], "canonical_url": ""}])
    )

    assert canonical.briefing.citations[0].url == "https://example.com/canonical"
    assert fallback.briefing.citations[0].url == "https://example.com/story"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "/relative",
        "https:///missing-host",
        "https://user:pass@example.com/story",
        "https://example.com:bad/story",
    ],
)
def test_build_get_omits_invalid_urls_and_dangling_content_ids(url: str) -> None:
    article = {**_row()["articles"][0], "canonical_url": url, "url": url}

    result = build_briefing_get_result(_row(articles=[article]))

    assert result.briefing.citations == []
    assert result.briefing.content.sections[0].citations == []
    assert result.briefing.content.worth_opening == []
    assert result.briefing.omitted_citations >= 1
    assert result.truncated is True


@pytest.mark.parametrize("content", [None, "oops", [], {"sections": "oops", "worth_opening": []}])
def test_build_get_degrades_malformed_top_level_content(content: Any) -> None:
    result = build_briefing_get_result(_row(content=content))

    assert result.briefing.content.model_dump() == {"sections": [], "worth_opening": []}
    assert result.briefing.content_truncated is True
    assert result.briefing.omitted_sections >= 1


def test_build_get_filters_malformed_sections_boolean_duplicates_and_invisible_ids() -> None:
    content = {
        "sections": [
            None,
            {
                "title": 123,
                "body": ["private"],
                "citations": [True, 11, 11, 12, -1, "11"],
                "unknown": "private",
            },
        ],
        "worth_opening": [True, 11, 11, 12, 0, "11"],
        "reading_list": "private",
    }

    result = build_briefing_get_result(_row(content=content))

    assert result.briefing.content.sections[0].model_dump() == {
        "title": "",
        "body": "",
        "citations": [11],
    }
    assert result.briefing.content.worth_opening == [11]
    assert result.briefing.omitted_sections >= 1
    assert result.briefing.omitted_citations >= 1
    assert result.briefing.content_truncated is True


def test_build_get_omits_malformed_and_duplicate_article_rows() -> None:
    valid = _row()["articles"][0]
    result = build_briefing_get_result(_row(articles=[None, {**valid, "id": True}, valid, valid]))

    assert [citation.article_id for citation in result.briefing.citations] == [11]
    assert result.briefing.omitted_citations >= 3
    assert result.truncated is True


def test_build_get_caps_fields_collections_and_exact_escaped_unicode_size() -> None:
    articles = [
        {
            **_row()["articles"][0],
            "id": article_id,
            "title": "\U0001f680\n" * 300,
            "source_name": "\u6e90" * 300,
            "url": f"https://example.com/{article_id}/" + "x" * 2_500,
        }
        for article_id in range(1, 40)
    ]
    sections = [
        {
            "title": "\u6bb5" * 300,
            "body": "\U0001f680\n" * 1_000,
            "citations": list(range(1, 40)),
        }
        for _ in range(20)
    ]

    result = build_briefing_get_result(
        _row(
            title="\U0001f680" * 500,
            summary="\u6e2c\n" * 1_000,
            scope="x" * 200,
            content={"sections": sections, "worth_opening": list(range(1, 40))},
            articles=articles,
        )
    )

    assert len(result.briefing.title) <= 240
    assert len(result.briefing.summary) <= 800
    assert len(result.briefing.scope) <= 80
    assert len(result.briefing.content.sections) <= 12
    assert len(result.briefing.citations) <= 25
    assert len(result.briefing.content.worth_opening) <= 25
    assert result.truncated is True
    assert _size(result) <= MCP_STRUCTURED_CONTENT_BYTES


def test_build_get_packs_complete_records_and_reports_omissions() -> None:
    articles = [
        {**_row()["articles"][0], "id": article_id, "title": "x" * 240}
        for article_id in range(1, 26)
    ]
    result = build_briefing_get_result(
        _row(
            content={
                "sections": [
                    {"title": "section", "body": "x" * 1_500, "citations": list(range(1, 26))}
                    for _ in range(12)
                ],
                "worth_opening": list(range(1, 26)),
            },
            articles=articles,
        )
    )

    assert all(section.title == "section" for section in result.briefing.content.sections)
    assert all(citation.url.startswith("https://") for citation in result.briefing.citations)
    assert result.briefing.omitted_sections + result.briefing.omitted_citations > 0
    assert result.briefing.content_truncated is True
    assert result.truncated is True
    assert _size(result) <= MCP_STRUCTURED_CONTENT_BYTES


def test_build_list_uses_lookahead_and_terminal_offsets() -> None:
    rows = [_row(id=row_id) for row_id in range(1, 4)]

    page = build_briefing_list_result(rows, offset=40, requested_limit=2)
    terminal = build_briefing_list_result(rows[:2], offset=40, requested_limit=2)

    assert [item.id for item in page.briefings] == [1, 2]
    assert page.next_offset == 42
    assert page.truncated is False
    assert terminal.next_offset is None
    assert set(page.model_dump()) == {"briefings", "next_offset", "truncated"}
    assert set(page.model_dump()["briefings"][0]) == {
        "id",
        "title",
        "summary",
        "scope",
        "since_at",
        "until_at",
        "created_at",
    }


def test_build_list_byte_resume_does_not_skip_first_unreturned_row() -> None:
    rows = [
        _row(id=row_id, title="\U0001f680" * 240, summary="\u6e2c" * 800) for row_id in range(1, 6)
    ]

    page = build_briefing_list_result(rows, offset=10, requested_limit=5)

    assert 0 < len(page.briefings) < 5
    assert page.next_offset == 10 + len(page.briefings)
    assert page.truncated is True
    assert _size(page) <= MCP_STRUCTURED_CONTENT_BYTES


@pytest.mark.parametrize(
    ("alias", "value"),
    [
        (BriefingId, 0),
        (BriefingId, True),
        (BriefingLimit, 0),
        (BriefingLimit, 26),
        (BriefingOffset, -1),
        (BriefingOffset, 10_001),
    ],
)
def test_briefing_input_aliases_reject_invalid_values(alias: Any, value: Any) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(alias).validate_python(value)
