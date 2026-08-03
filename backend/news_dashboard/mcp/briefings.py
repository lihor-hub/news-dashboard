from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from ipaddress import AddressValueError, ip_address
from typing import Any, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from news_dashboard.ingest.service import canonicalize_url

MCP_STRUCTURED_CONTENT_BYTES = 4_800
MAX_TITLE_LENGTH = 240
MAX_SUMMARY_LENGTH = 800
MAX_SCOPE_LENGTH = 80
MAX_SECTION_TITLE_LENGTH = 200
MAX_SECTION_BODY_LENGTH = 1_500
MAX_CITATION_SOURCE_LENGTH = 120
MAX_CITATION_URL_LENGTH = 2_048
MAX_SECTIONS = 12
MAX_CITATIONS = 25
MAX_WORTH_OPENING = 25
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


class _PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BriefingSummary(_PublicModel):
    id: int = Field(ge=1)
    title: str = Field(max_length=MAX_TITLE_LENGTH)
    summary: str = Field(max_length=MAX_SUMMARY_LENGTH)
    scope: str = Field(max_length=MAX_SCOPE_LENGTH)
    since_at: datetime | None
    until_at: datetime | None
    created_at: datetime


class BriefingSection(_PublicModel):
    title: str = Field(max_length=MAX_SECTION_TITLE_LENGTH)
    body: str = Field(max_length=MAX_SECTION_BODY_LENGTH)
    citations: list[int] = Field(max_length=MAX_CITATIONS)


class BriefingContent(_PublicModel):
    sections: list[BriefingSection] = Field(max_length=MAX_SECTIONS)
    worth_opening: list[int] = Field(max_length=MAX_WORTH_OPENING)


class BriefingCitation(_PublicModel):
    article_id: int = Field(ge=1)
    title: str = Field(max_length=MAX_TITLE_LENGTH)
    source: str = Field(max_length=MAX_CITATION_SOURCE_LENGTH)
    url: str = Field(max_length=MAX_CITATION_URL_LENGTH)
    section_index: int | None
    citation_index: int | None


class BriefingDetail(BriefingSummary):
    content: BriefingContent
    citations: list[BriefingCitation] = Field(max_length=MAX_CITATIONS)
    content_truncated: bool
    omitted_sections: int = Field(ge=0)
    omitted_citations: int = Field(ge=0)


class BriefingListResult(_PublicModel):
    briefings: list[BriefingSummary] = Field(max_length=MAX_CITATIONS)
    next_offset: int | None = Field(ge=0)
    truncated: bool


class BriefingGetResult(_PublicModel):
    briefing: BriefingDetail
    truncated: bool


def _text(value: Any, limit: int) -> tuple[str, bool]:
    if not isinstance(value, str):
        return "", value not in (None, "")
    return value[:limit], len(value) > limit


def _aware_datetime(value: Any, *, required: bool) -> datetime | None:
    parsed: datetime | None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            parsed = None
    else:
        parsed = None
    if parsed is None:
        return datetime.fromtimestamp(0, tz=timezone.utc) if required else None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _positive_ids(value: Any) -> tuple[list[int], int]:
    if not isinstance(value, list):
        return [], 1
    accepted: list[int] = []
    seen: set[int] = set()
    omitted = 0
    for candidate in value:
        if (
            isinstance(candidate, bool)
            or not isinstance(candidate, int)
            or candidate <= 0
            or candidate in seen
        ):
            omitted += 1
            continue
        seen.add(candidate)
        accepted.append(candidate)
    return accepted, omitted


def _valid_hostname(hostname: str) -> bool:
    if not hostname or hostname.startswith(".") or hostname.endswith(".") or ".." in hostname:
        return False
    if ":" in hostname or all(character.isdigit() or character == "." for character in hostname):
        try:
            ip_address(hostname)
        except (AddressValueError, ValueError):
            return False
        return True
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
        decoded_hostname = ascii_hostname.encode("ascii").decode("idna")
    except UnicodeError:
        return False
    if len(ascii_hostname) > 253 or (not hostname.isascii() and decoded_hostname != hostname):
        return False
    return all(_DNS_LABEL.fullmatch(label) is not None for label in ascii_hostname.split("."))


def _normalized_url(article: Mapping[str, Any]) -> str | None:
    canonical = article.get("canonical_url")
    raw = canonical if isinstance(canonical, str) and canonical.strip() else article.get("url")
    if not isinstance(raw, str) or not raw.strip():
        return None
    if any(ord(character) < 32 for character in raw):
        return None
    try:
        normalized = canonicalize_url(raw)
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
        port = parsed.port
        normalized_bytes = normalized.encode()
    except (UnicodeError, ValueError):
        return None
    if (
        len(normalized_bytes) > MAX_CITATION_URL_LENGTH
        or parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or "%" in parsed.netloc
        or "\x00" in parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or port == 0
        or not _valid_hostname(hostname)
    ):
        return None
    return normalized


def _summary(row: Mapping[str, Any]) -> tuple[BriefingSummary, bool]:
    title, title_cut = _text(row.get("title"), MAX_TITLE_LENGTH)
    summary, summary_cut = _text(row.get("summary"), MAX_SUMMARY_LENGTH)
    scope, scope_cut = _text(row.get("scope"), MAX_SCOPE_LENGTH)
    row_id = row.get("id")
    if isinstance(row_id, bool) or not isinstance(row_id, int):
        row_id = 0
    return (
        BriefingSummary(
            id=row_id,
            title=title,
            summary=summary,
            scope=scope,
            since_at=_aware_datetime(row.get("since_at"), required=False),
            until_at=_aware_datetime(row.get("until_at"), required=False),
            created_at=cast("datetime", _aware_datetime(row.get("created_at"), required=True)),
        ),
        title_cut or summary_cut or scope_cut,
    )


def _json_size(value: BaseModel) -> int:
    return len(
        json.dumps(
            value.model_dump(mode="json"),
            default=str,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode()
    )


def _normalize_citations(value: Any) -> tuple[list[BriefingCitation], int, bool]:
    if not isinstance(value, list):
        return [], 1, True
    citations: list[BriefingCitation] = []
    seen: set[int] = set()
    omitted = 0
    truncated = False
    for raw in value:
        if not isinstance(raw, Mapping):
            omitted += 1
            truncated = True
            continue
        article_id = raw.get("id")
        if (
            isinstance(article_id, bool)
            or not isinstance(article_id, int)
            or article_id <= 0
            or article_id in seen
        ):
            omitted += 1
            truncated = True
            continue
        url = _normalized_url(raw)
        if url is None:
            omitted += 1
            truncated = True
            continue
        if len(citations) >= MAX_CITATIONS:
            omitted += 1
            truncated = True
            continue
        seen.add(article_id)
        title, title_cut = _text(raw.get("title"), MAX_TITLE_LENGTH)
        source, source_cut = _text(raw.get("source_name"), MAX_CITATION_SOURCE_LENGTH)
        section_index = raw.get("section_index")
        citation_index = raw.get("citation_index")
        citations.append(
            BriefingCitation(
                article_id=article_id,
                title=title,
                source=source,
                url=url,
                section_index=(
                    section_index
                    if isinstance(section_index, int) and not isinstance(section_index, bool)
                    else None
                ),
                citation_index=(
                    citation_index
                    if isinstance(citation_index, int) and not isinstance(citation_index, bool)
                    else None
                ),
            )
        )
        truncated = truncated or title_cut or source_cut
    return citations, omitted, truncated


def _normalize_content(
    value: Any, visible_ids: set[int]
) -> tuple[list[BriefingSection], list[int], int, int, bool]:
    if (
        not isinstance(value, Mapping)
        or not isinstance(value.get("sections"), list)
        or not isinstance(value.get("worth_opening"), list)
    ):
        return [], [], 1, 0, True
    sections: list[BriefingSection] = []
    omitted_sections = 0
    omitted_citations = 0
    truncated = False
    for raw in value["sections"]:
        if not isinstance(raw, Mapping):
            omitted_sections += 1
            truncated = True
            continue
        ids, invalid_count = _positive_ids(raw.get("citations"))
        filtered_ids = [article_id for article_id in ids if article_id in visible_ids]
        omitted_citations += invalid_count + len(ids) - len(filtered_ids)
        if len(sections) >= MAX_SECTIONS:
            omitted_sections += 1
            omitted_citations += len(filtered_ids)
            truncated = True
            continue
        title, title_cut = _text(raw.get("title"), MAX_SECTION_TITLE_LENGTH)
        body, body_cut = _text(raw.get("body"), MAX_SECTION_BODY_LENGTH)
        sections.append(BriefingSection(title=title, body=body, citations=filtered_ids))
        truncated = (
            truncated or title_cut or body_cut or invalid_count > 0 or len(ids) != len(filtered_ids)
        )
    worth, invalid_worth = _positive_ids(value["worth_opening"])
    visible_worth = [article_id for article_id in worth if article_id in visible_ids]
    omitted_citations += invalid_worth + len(worth) - len(visible_worth)
    if len(visible_worth) > MAX_WORTH_OPENING:
        omitted_citations += len(visible_worth) - MAX_WORTH_OPENING
        visible_worth = visible_worth[:MAX_WORTH_OPENING]
        truncated = True
    return sections, visible_worth, omitted_sections, omitted_citations, truncated


def _detail_result(
    summary: BriefingSummary,
    sections: list[BriefingSection],
    worth_opening: list[int],
    citations: list[BriefingCitation],
    omitted_sections: int,
    omitted_citations: int,
    truncated: bool,
) -> BriefingGetResult:
    detail = BriefingDetail(
        **summary.model_dump(),
        content=BriefingContent(sections=sections, worth_opening=worth_opening),
        citations=citations,
        content_truncated=truncated,
        omitted_sections=omitted_sections,
        omitted_citations=omitted_citations,
    )
    return BriefingGetResult(briefing=detail, truncated=truncated)


def _filter_content_to_citations(
    sections: list[BriefingSection], worth_opening: list[int], citations: list[BriefingCitation]
) -> tuple[list[BriefingSection], list[int]]:
    ids = {citation.article_id for citation in citations}
    return (
        [
            section.model_copy(
                update={
                    "citations": [
                        article_id for article_id in section.citations if article_id in ids
                    ]
                }
            )
            for section in sections
        ],
        [article_id for article_id in worth_opening if article_id in ids],
    )


def build_briefing_get_result(row: dict[str, Any]) -> BriefingGetResult:
    summary, summary_cut = _summary(row)
    citations, omitted_citations, citation_cut = _normalize_citations(row.get("articles"))
    sections, worth, omitted_sections, content_omitted, content_cut = _normalize_content(
        row.get("content"), {citation.article_id for citation in citations}
    )
    omitted_citations += content_omitted
    truncated = summary_cut or citation_cut or content_cut
    sections, worth = _filter_content_to_citations(sections, worth, citations)
    result = _detail_result(
        summary,
        sections,
        worth,
        citations,
        omitted_sections,
        omitted_citations,
        truncated,
    )
    while _json_size(result) > MCP_STRUCTURED_CONTENT_BYTES and citations:
        removed_citation = citations.pop()
        omitted_citations += 1
        removed_references = sum(
            removed_citation.article_id in section.citations for section in sections
        )
        removed_references += int(removed_citation.article_id in worth)
        omitted_citations += removed_references
        sections, worth = _filter_content_to_citations(sections, worth, citations)
        truncated = True
        result = _detail_result(
            summary,
            sections,
            worth,
            citations,
            omitted_sections,
            omitted_citations,
            truncated,
        )
    while _json_size(result) > MCP_STRUCTURED_CONTENT_BYTES and sections:
        removed_section = sections.pop()
        omitted_sections += 1
        omitted_citations += len(removed_section.citations)
        truncated = True
        result = _detail_result(
            summary,
            sections,
            worth,
            citations,
            omitted_sections,
            omitted_citations,
            truncated,
        )
    while _json_size(result) > MCP_STRUCTURED_CONTENT_BYTES and worth:
        worth.pop()
        omitted_citations += 1
        truncated = True
        result = _detail_result(
            summary,
            sections,
            worth,
            citations,
            omitted_sections,
            omitted_citations,
            truncated,
        )
    while _json_size(result) > MCP_STRUCTURED_CONTENT_BYTES:
        fields = ("summary", "title", "scope")
        field = max(fields, key=lambda name: len(getattr(summary, name)))
        value = getattr(summary, field)
        if not value:
            message = "Briefing metadata exceeds structured content budget"
            raise ValueError(message)
        shortened = value[: max(0, len(value) - max(1, len(value) // 8))]
        summary = summary.model_copy(update={field: shortened})
        truncated = True
        result = _detail_result(
            summary,
            sections,
            worth,
            citations,
            omitted_sections,
            omitted_citations,
            truncated,
        )
    return result


def build_briefing_list_result(
    rows: list[dict[str, Any]], *, offset: int, requested_limit: int
) -> BriefingListResult:
    page_rows = rows[:requested_limit]
    has_lookahead = len(rows) > requested_limit
    accepted: list[BriefingSummary] = []
    truncated = False
    byte_stopped = False
    for row in page_rows:
        summary, summary_cut = _summary(row)
        candidate = BriefingListResult(
            briefings=[*accepted, summary],
            next_offset=offset + len(accepted) + 1,
            truncated=truncated or summary_cut,
        )
        while _json_size(candidate) > MCP_STRUCTURED_CONTENT_BYTES:
            field = max(("summary", "title", "scope"), key=lambda name: len(getattr(summary, name)))
            value = getattr(summary, field)
            if not value:
                byte_stopped = True
                break
            summary = summary.model_copy(
                update={field: value[: max(0, len(value) - max(1, len(value) // 8))]}
            )
            summary_cut = True
            candidate = BriefingListResult(
                briefings=[*accepted, summary],
                next_offset=offset + len(accepted) + 1,
                truncated=True,
            )
        if byte_stopped:
            break
        accepted.append(summary)
        truncated = truncated or summary_cut
    if len(accepted) < len(page_rows):
        byte_stopped = True
        truncated = True
    more = byte_stopped or has_lookahead
    return BriefingListResult(
        briefings=accepted,
        next_offset=offset + len(accepted) if more else None,
        truncated=truncated,
    )
