"""Tests for shared public web-content extraction models and quality gates."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from news_dashboard.body_fetch import extract_public_content
from news_dashboard.content_extraction import (
    ExtractionAttempt,
    ExtractionResult,
    assess_extracted_text,
)


@pytest.mark.parametrize(
    ("text", "expected_reasons"),
    [
        ("", ("too_short", "too_few_words", "too_few_blocks")),
        (
            "The Python Tutorial — Python 3.14.6 documentation",
            ("too_short", "too_few_words", "too_few_blocks"),
        ),
        (
            "Access denied. Verify you are human to continue.",
            ("too_short", "too_few_words", "too_few_blocks", "failure_page"),
        ),
    ],
)
def test_assess_extracted_text_rejects_low_quality_candidates(
    text: str, expected_reasons: tuple[str, ...]
) -> None:
    quality = assess_extracted_text(text)

    assert quality.accepted is False
    assert quality.rejection_reasons == expected_reasons


def test_assess_extracted_text_accepts_two_meaningful_paragraphs() -> None:
    paragraph = (
        "Readable article content explains a useful technical idea with enough detail "
        "for a learner to understand the context, tradeoffs, and practical consequences."
    )
    quality = assess_extracted_text(f"{paragraph}\n\n{paragraph}")

    assert quality.accepted is True
    assert quality.meaningful_block_count == 2
    assert quality.rejection_reasons == ()


def test_assess_extracted_text_accepts_one_long_paragraph() -> None:
    text = "meaningful article word " * 30
    quality = assess_extracted_text(text)

    assert len(text) >= 600
    assert quality.accepted is True
    assert quality.meaningful_block_count == 1


def test_extraction_result_carries_immutable_attempts() -> None:
    quality = assess_extracted_text("meaningful article word " * 30)
    attempt = ExtractionAttempt(
        method="static",
        status="accepted",
        latency_ms=12,
        quality=quality,
    )
    result = ExtractionResult.success(
        text="meaningful article word " * 30,
        method="static",
        quality=quality,
        attempts=(attempt,),
    )

    assert result.status == "ok"
    assert result.method == "static"
    assert result.failure_reason is None
    assert result.attempts == (attempt,)
    assert isinstance(hash(result), int)


def test_extraction_result_failure_has_no_text_or_method() -> None:
    attempt = ExtractionAttempt(
        method="static",
        status="failed",
        latency_ms=4,
        failure_reason="not_found",
    )
    result = ExtractionResult.failure(
        failure_reason="not_found",
        attempts=(attempt,),
    )

    assert result.status == "error"
    assert result.text == ""
    assert result.method is None
    assert result.quality is None
    assert result.failure_reason == "not_found"


def test_public_url_does_not_fall_back_to_selenium_without_egress_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_RENDERER_EGRESS_PROXY", raising=False)

    with (
        patch(
            "news_dashboard.body_fetch._static_extract_body",
            return_value=("Page title", "ok", None),
        ),
        patch(
            "news_dashboard.selenium_client.fetch_spa_html",
            return_value="<html><body></body></html>",
        ) as fetch_spa_html,
    ):
        result = extract_public_content(
            "https://example.com/article",
            allow_ai=False,
            allow_crawl4ai=False,
        )

    assert result.status == "error"
    fetch_spa_html.assert_not_called()
