from __future__ import annotations

import ipaddress
import json
import re
from typing import Any, TypedDict
from urllib.parse import SplitResult, urlsplit

import idna

from news_dashboard.ingest.service import canonicalize_url

ASK_STRUCTURED_CONTENT_BYTES = 4_800
_MAX_CITATION_TITLE_BYTES = 512
_MAX_CITATION_URL_BYTES = 2_048
_BRACKET_POSITION = re.compile(r"(?<!\[)\[([1-9][0-9]{0,18})\](?!\])")
_TRACE_ID = re.compile(r"[0-9a-fA-F]{32}")


class AskCitation(TypedDict):
    id: int
    title: str
    url: str


class AskNewsResult(TypedDict):
    answer: str
    citations: list[AskCitation]
    trace_id: str | None
    truncated: bool


def _utf8_prefix(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _valid_host(host: str) -> bool:
    if ":" in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return False
        return True
    if all(character.isdigit() or character == "." for character in host):
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            return False
        return True
    candidate = host[:-1] if host.endswith(".") else host
    try:
        ascii_host = idna.encode(candidate, uts46=False, std3_rules=True)
    except idna.IDNAError:
        return False
    return bool(ascii_host) and len(ascii_host) <= 253


def _safe_http_url_parts(value: str) -> SplitResult | None:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except (UnicodeError, ValueError):
        return None
    empty_port = parsed.netloc.endswith(":")
    if parsed.netloc.startswith("[") and "]" in parsed.netloc:
        empty_port = parsed.netloc.partition("]")[2] == ":"
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or "%" in parsed.netloc
        or empty_port
        or (port is not None and not 1 <= port <= 65_535)
        or not _valid_host(hostname)
    ):
        return None
    return parsed


def _normalized_url(value: object) -> tuple[str | None, bool]:
    if isinstance(value, str) and len(value) > 16_384:
        return None, True
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(character.isspace() or ord(character) < 32 for character in value)
        or _safe_http_url_parts(value) is None
    ):
        return None, False
    try:
        normalized = canonicalize_url(value)
    except (UnicodeError, ValueError):
        return None, False
    if _safe_http_url_parts(normalized) is None:
        return None, False
    if len(normalized.encode("utf-8")) > _MAX_CITATION_URL_BYTES:
        return None, True
    return normalized, False


def _citation(source: object) -> tuple[AskCitation | None, bool]:
    if not isinstance(source, dict):
        return None, False
    article_id = source.get("id")
    title = source.get("title")
    if (
        isinstance(article_id, bool)
        or not isinstance(article_id, int)
        or article_id <= 0
        or not isinstance(title, str)
        or not title.strip()
    ):
        return None, False
    url, url_omitted = _normalized_url(source.get("url"))
    if url is None:
        return None, url_omitted
    stripped_title = title.strip()
    bounded_title = _utf8_prefix(stripped_title, _MAX_CITATION_TITLE_BYTES).strip()
    if not bounded_title:
        return None, False
    return (
        {"id": article_id, "title": bounded_title, "url": url},
        bounded_title != stripped_title,
    )


def _structured_size(result: AskNewsResult) -> int:
    return len(json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))


def _bounded_answer(result: AskNewsResult, answer: str) -> str:
    low = 0
    high = len(answer)
    best = ""
    while low <= high:
        middle = (low + high) // 2
        candidate = answer[:middle]
        result["answer"] = candidate
        if _structured_size(result) <= ASK_STRUCTURED_CONTENT_BYTES:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    result["answer"] = best
    return best


def shape_ask_result(raw_result: dict[str, Any]) -> AskNewsResult:
    """Validate untrusted generated citations and return a bounded typed result."""
    raw_answer = raw_result.get("answer")
    answer = raw_answer if isinstance(raw_answer, str) else ""
    raw_sources = raw_result.get("sources")
    sources = raw_sources if isinstance(raw_sources, list) else []
    citations: list[AskCitation] = []
    cited_article_ids: set[int] = set()
    truncated = False
    for match in _BRACKET_POSITION.finditer(answer):
        position = int(match.group(1))
        if position > len(sources):
            continue
        citation, citation_truncated = _citation(sources[position - 1])
        truncated = truncated or citation_truncated
        if citation is None:
            continue
        if citation["id"] in cited_article_ids:
            continue
        cited_article_ids.add(citation["id"])
        citations.append(citation)
        truncated = truncated or citation_truncated

    raw_trace_id = raw_result.get("trace_id")
    trace_id = (
        raw_trace_id.lower()
        if isinstance(raw_trace_id, str) and _TRACE_ID.fullmatch(raw_trace_id)
        else None
    )
    result: AskNewsResult = {
        "answer": answer,
        "citations": citations,
        "trace_id": trace_id,
        "truncated": truncated,
    }
    while citations and _structured_size(result) > ASK_STRUCTURED_CONTENT_BYTES:
        citations.pop()
        result["truncated"] = True
    if _structured_size(result) > ASK_STRUCTURED_CONTENT_BYTES:
        result["truncated"] = True
        _bounded_answer(result, answer)
    return result
