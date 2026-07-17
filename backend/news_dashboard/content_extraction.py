"""Typed results and deterministic quality gates for public web content."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Self

ExtractionMethod = Literal["static", "selenium", "crawl4ai", "ai"]
FailureReason = Literal[
    "unsafe_url",
    "not_found",
    "blocked",
    "fetch_failed",
    "non_html",
    "render_failed",
    "no_readable_content",
]
AttemptStatus = Literal["accepted", "rejected", "failed"]
ExtractionStatus = Literal["ok", "error"]

MIN_CHARACTER_COUNT = 200
MIN_WORD_COUNT = 40
MIN_MEANINGFUL_BLOCK_COUNT = 2
MIN_SINGLE_BLOCK_CHARACTER_COUNT = 600
MIN_MEANINGFUL_BLOCK_LENGTH = 40

_WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
_FAILURE_PAGE_SIGNALS = (
    "access denied",
    "verify you are human",
    "captcha",
    "sign in to continue",
    "login required",
)
_FAILURE_PAGE_MAX_LENGTH = 600


@dataclass(frozen=True)
class QualityEvidence:
    """Deterministic evidence used to accept or reject extracted text."""

    character_count: int
    word_count: int
    meaningful_block_count: int
    accepted: bool
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionAttempt:
    """Bounded diagnostic information for one extraction method."""

    method: ExtractionMethod
    status: AttemptStatus
    latency_ms: int
    quality: QualityEvidence | None = None
    failure_reason: FailureReason | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ExtractionResult:
    """Final result of the ordered public-content extraction pipeline."""

    status: ExtractionStatus
    text: str
    method: ExtractionMethod | None
    quality: QualityEvidence | None
    attempts: tuple[ExtractionAttempt, ...]
    failure_reason: FailureReason | None

    @classmethod
    def success(
        cls,
        *,
        text: str,
        method: ExtractionMethod,
        quality: QualityEvidence,
        attempts: tuple[ExtractionAttempt, ...],
    ) -> Self:
        return cls(
            status="ok",
            text=text,
            method=method,
            quality=quality,
            attempts=attempts,
            failure_reason=None,
        )

    @classmethod
    def failure(
        cls,
        *,
        failure_reason: FailureReason,
        attempts: tuple[ExtractionAttempt, ...],
    ) -> Self:
        return cls(
            status="error",
            text="",
            method=None,
            quality=None,
            attempts=attempts,
            failure_reason=failure_reason,
        )


def _normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def assess_extracted_text(text: str) -> QualityEvidence:
    """Assess whether extracted text is substantial enough for downstream use."""
    normalized = _normalize_text(text)
    character_count = len(normalized)
    word_count = len(_WORD_RE.findall(normalized))
    blocks = [
        block.strip()
        for block in normalized.split("\n\n")
        if len(block.strip()) >= MIN_MEANINGFUL_BLOCK_LENGTH
    ]
    meaningful_block_count = len(blocks)

    reasons: list[str] = []
    if character_count < MIN_CHARACTER_COUNT:
        reasons.append("too_short")
    if word_count < MIN_WORD_COUNT:
        reasons.append("too_few_words")
    if (
        meaningful_block_count < MIN_MEANINGFUL_BLOCK_COUNT
        and character_count < MIN_SINGLE_BLOCK_CHARACTER_COUNT
    ):
        reasons.append("too_few_blocks")

    lowered = normalized.casefold()
    if character_count < _FAILURE_PAGE_MAX_LENGTH and any(
        signal in lowered for signal in _FAILURE_PAGE_SIGNALS
    ):
        reasons.append("failure_page")

    return QualityEvidence(
        character_count=character_count,
        word_count=word_count,
        meaningful_block_count=meaningful_block_count,
        accepted=not reasons,
        rejection_reasons=tuple(reasons),
    )
