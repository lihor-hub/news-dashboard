"""Bounded deep-research enrichment for canonical briefing email sections."""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, cast
from urllib.parse import urlsplit

import httpx
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

from news_dashboard import ai_client
from news_dashboard.db import connect

_MAX_RESEARCH_STORIES = 5
_MAX_WEB_SEARCHES = 8
_MAX_PAGE_FETCHES = 12
_MAX_PAGE_CHARACTERS = 24_000
_MAX_MODEL_CALLS = 16
_MAX_RESEARCH_SECONDS = 120.0
_MAX_OUTPUT_BYTES = 24_000
_TAVILY_ENDPOINT = "https://api.tavily.com/search"
logger = logging.getLogger(__name__)


class InvalidEnrichmentError(ValueError):
    """Raised when agent output crosses the email enrichment boundary."""


class ResearchBudgetError(RuntimeError):
    """Raised when a research run exhausts a hard resource budget."""


class ExternalCitation(BaseModel):
    """One external source supporting an enriched section."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=180)
    publisher: str = Field(min_length=1, max_length=120)
    url: HttpUrl


class SectionEnrichment(BaseModel):
    """Validated research metadata for one canonical briefing section."""

    model_config = ConfigDict(extra="forbid")

    section_index: int = Field(ge=0)
    key_takeaways: list[str] = Field(min_length=1, max_length=3)
    context: str = Field(min_length=1, max_length=800)
    evidence_status: Literal["corroborated", "mixed", "uncertain"]
    evidence_summary: str = Field(min_length=1, max_length=600)
    related_information: str = Field(max_length=600)
    why_it_matters: str = Field(min_length=1, max_length=500)
    citations: list[ExternalCitation] = Field(min_length=1, max_length=5)


class BriefingResearchResult(BaseModel):
    """Structured output contract returned by the Deep Agent supervisor."""

    model_config = ConfigDict(extra="forbid")

    sections: list[SectionEnrichment] = Field(min_length=1, max_length=_MAX_RESEARCH_STORIES)


@dataclass(frozen=True, slots=True)
class ResearchSource:
    """One canonical article used to seed external research."""

    article_id: int
    title: str
    url: str
    source_name: str
    summary: str


@dataclass(frozen=True, slots=True)
class ResearchSection:
    """One canonical briefing section eligible for research."""

    section_index: int
    title: str
    body: str
    sources: tuple[ResearchSource, ...]


def _mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast("Mapping[str, Any]", item) for item in value if isinstance(item, Mapping)]


def select_research_sections(briefing: Mapping[str, Any]) -> list[ResearchSection]:
    """Select at most five sourced sections in canonical briefing order."""
    content = briefing.get("content")
    sections = _mappings(content.get("sections")) if isinstance(content, Mapping) else []
    article_rows = _mappings(briefing.get("articles"))
    articles = {article.get("id"): article for article in article_rows}
    selected: list[ResearchSection] = []
    for section_index, section in enumerate(sections):
        citations = section.get("citations")
        sources: list[ResearchSource] = []
        if isinstance(citations, list):
            for article_id in citations:
                article = articles.get(article_id)
                if article is None or not isinstance(article_id, int):
                    continue
                sources.append(
                    ResearchSource(
                        article_id=article_id,
                        title=str(article.get("title") or ""),
                        url=str(article.get("url") or ""),
                        source_name=str(article.get("source_name") or ""),
                        summary=str(article.get("summary") or ""),
                    )
                )
        if not sources:
            continue
        selected.append(
            ResearchSection(
                section_index=section_index,
                title=str(section.get("title") or ""),
                body=str(section.get("body") or ""),
                sources=tuple(sources),
            )
        )
        if len(selected) == _MAX_RESEARCH_STORIES:
            break
    return selected


def _public_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host:
            return False
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return address.is_global


def validate_research_result(
    briefing: Mapping[str, Any],
    payload: object,
    *,
    fetched_urls: set[str] | None = None,
) -> dict[str, Any]:
    """Validate structured output against selected sections and safe citations."""
    try:
        result = BriefingResearchResult.model_validate(payload)
    except ValidationError as exc:
        msg = "Invalid research enrichment structure"
        raise InvalidEnrichmentError(msg) from exc
    selected = select_research_sections(briefing)
    allowed_indexes = {section.section_index for section in selected}
    seen: set[int] = set()
    for section in result.sections:
        if section.section_index not in allowed_indexes or section.section_index in seen:
            msg = "Research enrichment references an invalid section"
            raise InvalidEnrichmentError(msg)
        seen.add(section.section_index)
        if any(not _public_http_url(str(citation.url)) for citation in section.citations):
            msg = "Research enrichment contains an unsafe citation"
            raise InvalidEnrichmentError(msg)
        if fetched_urls is not None and any(
            str(citation.url) not in fetched_urls for citation in section.citations
        ):
            msg = "Research enrichment contains an unverified citation"
            raise InvalidEnrichmentError(msg)
    if seen != allowed_indexes:
        msg = "Research enrichment must cover every selected section"
        raise InvalidEnrichmentError(msg)
    return result.model_dump(mode="json")


def load_completed_enrichment(
    user_id: int,
    briefing_id: int,
    *,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Load a reusable completed enrichment scoped to its owning user."""
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            SELECT content FROM briefing_email_enrichments
            WHERE user_id = %s AND briefing_id = %s AND status = 'complete'
            """,
            (user_id, briefing_id),
        ).fetchone()
    if row is None or not isinstance(row["content"], dict):
        return None
    return cast("dict[str, Any]", row["content"])


def save_completed_enrichment(
    *,
    user_id: int,
    briefing_id: int,
    content: dict[str, Any],
    model: str,
    database_url: str | None = None,
) -> None:
    """Persist validated enrichment for idempotent preview and delivery reuse."""
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO briefing_email_enrichments(
                user_id, briefing_id, status, content, model
            ) VALUES (%s, %s, 'complete', %s, %s)
            ON CONFLICT (user_id, briefing_id) DO UPDATE SET
                status = 'complete', content = EXCLUDED.content, model = EXCLUDED.model,
                error_code = NULL, updated_at = NOW()
            """,
            (user_id, briefing_id, Jsonb(content), model),
        )


def _claim_run(user_id: int, briefing_id: int, *, database_url: str | None = None) -> bool:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO briefing_email_enrichments(user_id, briefing_id, status)
            VALUES (%s, %s, 'running')
            ON CONFLICT (user_id, briefing_id) DO UPDATE SET
                status = 'running', content = NULL, error_code = NULL,
                attempt_count = briefing_email_enrichments.attempt_count + 1,
                updated_at = NOW()
            WHERE briefing_email_enrichments.status IN ('failed', 'skipped')
               OR (briefing_email_enrichments.status = 'running'
                   AND briefing_email_enrichments.updated_at < NOW() - INTERVAL '5 minutes')
            RETURNING id
            """,
            (user_id, briefing_id),
        ).fetchone()
    return row is not None


def _record_skipped(
    user_id: int,
    briefing_id: int,
    error_code: str,
    *,
    database_url: str | None = None,
) -> None:
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO briefing_email_enrichments(user_id, briefing_id, status, error_code)
            VALUES (%s, %s, 'skipped', %s)
            ON CONFLICT (user_id, briefing_id) DO UPDATE SET
                status = 'skipped', content = NULL, error_code = EXCLUDED.error_code,
                updated_at = NOW()
            WHERE briefing_email_enrichments.status <> 'complete'
            """,
            (user_id, briefing_id, error_code),
        )


def _record_failure(
    user_id: int,
    briefing_id: int,
    error_code: str,
    *,
    database_url: str | None = None,
) -> None:
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            UPDATE briefing_email_enrichments
            SET status = 'failed', content = NULL, error_code = %s, updated_at = NOW()
            WHERE user_id = %s AND briefing_id = %s
            """,
            (error_code, user_id, briefing_id),
        )


def _personalization_context(
    user_id: int, *, database_url: str | None = None
) -> dict[str, list[str]]:
    with connect(database_url=database_url) as conn:
        profile = conn.execute(
            "SELECT interests FROM user_interest_profiles WHERE user_id = %s", (user_id,)
        ).fetchone()
        source_rows = conn.execute(
            """
            SELECT s.name FROM sources s
            LEFT JOIN user_sources us ON us.source_slug = s.slug AND us.user_id = %s
            WHERE COALESCE(us.enabled, s.enabled) = TRUE
            ORDER BY s.name
            LIMIT 100
            """,
            (user_id,),
        ).fetchall()
    interests_value = profile["interests"] if profile is not None else []
    interests = [str(item) for item in interests_value] if isinstance(interests_value, list) else []
    return {
        "interests": interests[:20],
        "subscribed_sources": [str(row["name"]) for row in source_rows],
    }


@dataclass(slots=True)
class _ResearchBudget:
    searches: int = 0
    page_fetches: int = 0
    model_calls: int = 0
    deadline: float = field(default_factory=lambda: time.monotonic() + _MAX_RESEARCH_SECONDS)
    fetched_urls: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def claim_search(self) -> None:
        with self.lock:
            self._check_deadline()
            if self.searches >= _MAX_WEB_SEARCHES:
                msg = "Web-search budget exhausted"
                raise ResearchBudgetError(msg)
            self.searches += 1

    def claim_page(self) -> None:
        with self.lock:
            self._check_deadline()
            if self.page_fetches >= _MAX_PAGE_FETCHES:
                msg = "Web-page budget exhausted"
                raise ResearchBudgetError(msg)
            self.page_fetches += 1

    def claim_model(self) -> None:
        with self.lock:
            self._check_deadline()
            if self.model_calls >= _MAX_MODEL_CALLS:
                msg = "Model-call budget exhausted"
                raise ResearchBudgetError(msg)
            self.model_calls += 1

    def record_fetched(self, url: str) -> None:
        with self.lock:
            self.fetched_urls.add(url)

    def check_complete(self) -> None:
        with self.lock:
            self._check_deadline()

    def _check_deadline(self) -> None:
        if time.monotonic() > self.deadline:
            msg = "Research runtime budget exhausted"
            raise ResearchBudgetError(msg)


def _research_tools(tavily_api_key: str, budget: _ResearchBudget) -> list[Any]:
    from langchain_core.tools import tool

    @tool
    def web_search(query: str) -> str:
        """Search the public web for independent evidence; returns at most five results."""
        budget.claim_search()
        response = httpx.post(
            _TAVILY_ENDPOINT,
            json={
                "api_key": tavily_api_key,
                "query": query[:500],
                "max_results": 5,
                "search_depth": "advanced",
                "include_raw_content": False,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        safe_results = [
            {
                "title": str(item.get("title") or "")[:180],
                "url": str(item.get("url") or ""),
                "content": str(item.get("content") or "")[:2_000],
            }
            for item in results[:5]
            if isinstance(item, dict) and _public_http_url(str(item.get("url") or ""))
        ]
        return json.dumps(safe_results)

    @tool
    def fetch_web_page(url: str) -> str:
        """Fetch bounded readable content from one public HTTP(S) research source."""
        budget.claim_page()
        from news_dashboard.body_fetch import extract_public_content

        result = extract_public_content(url, allow_ai=False, allow_crawl4ai=False)
        if result.status != "ok":
            return f"Page unavailable: {result.failure_reason}"
        budget.record_fetched(url)
        return result.text[:_MAX_PAGE_CHARACTERS]

    return [web_search, fetch_web_page]


def _model_configs() -> list[tuple[str, str | None]]:
    primary = ai_client.free_llm_config()
    fallback = ai_client.openai_config()
    configs: list[tuple[str, str | None]] = []
    for item in (primary, fallback):
        if item[0] and item not in configs:
            configs.append(item)
    return configs


def _invoke_deep_research(
    sections: list[ResearchSection],
    personalization: dict[str, list[str]],
    *,
    user_id: int,
    briefing_id: int,
) -> tuple[dict[str, Any], set[str]]:
    from deepagents import create_deep_agent
    from langchain_openai import ChatOpenAI
    from openai import OpenAIError

    tavily_api_key = os.environ["TAVILY_API_KEY"]
    model_name = (
        os.getenv("OPENAI_BRIEFING_ENRICHMENT_MODEL")
        or os.getenv("OPENAI_BRIEFING_MODEL")
        or "gpt-4o-mini"
    )
    section_payload = [
        {
            "section_index": section.section_index,
            "title": section.title,
            "body": section.body,
            "sources": [asdict(source) for source in section.sources],
        }
        for section in sections
    ]
    request = (
        "Research the supplied canonical briefing sections. Delegate focused web research, "
        "prefer primary and independent sources, distinguish corroboration from disagreement "
        "or uncertainty, and never invent evidence. Return structured enrichment only.\n\n"
        f"Sections: {json.dumps(section_payload)}\n"
        f"Configured personalization: {json.dumps(personalization)}"
    )
    last_error: Exception | None = None
    budget = _ResearchBudget()
    tools = _research_tools(tavily_api_key, budget)
    for api_key, base_url in _model_configs():
        model_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "model": model_name,
            "timeout": ai_client.request_timeout_seconds(),
            "temperature": 0,
        }
        if base_url is not None:
            model_kwargs["base_url"] = base_url
        model = ChatOpenAI(**model_kwargs)
        from langchain.agents.middleware import wrap_model_call

        @wrap_model_call
        def enforce_model_budget(request: Any, handler: Any) -> Any:
            budget.claim_model()
            return handler(request)

        agent = create_deep_agent(
            model=model,
            tools=[],
            system_prompt=(
                "You coordinate bounded email research. Use the web-researcher subagent for "
                "external research. Do not treat search snippets as proof; fetch important pages. "
                "Every enriched section needs at least one safe external citation."
            ),
            subagents=[
                {
                    "name": "web-researcher",
                    "description": (
                        "Researches selected briefing sections using bounded public web tools."
                    ),
                    "system_prompt": (
                        "Research only the assigned section. Use at most three searches and four "
                        "page fetches. Prefer primary documents and independent corroboration. "
                        "Return concise findings with exact source URLs; do not make unsupported "
                        "claims."
                    ),
                    "tools": tools,
                    "model": model,
                    "middleware": [enforce_model_budget],
                }
            ],
            middleware=[enforce_model_budget],
            response_format=BriefingResearchResult,
        )
        callbacks: list[Any] = []
        if ai_client.langfuse_enabled():
            from langfuse.langchain import CallbackHandler

            callbacks.append(CallbackHandler())
        try:
            from langfuse import propagate_attributes

            with propagate_attributes(
                user_id=str(user_id),
                session_id=f"briefing-email-enrichment:{user_id}:{briefing_id}",
                tags=["briefing", "email", "deep-research"],
                trace_name="briefing-email-enrichment",
            ):
                state = agent.invoke(
                    {"messages": [{"role": "user", "content": request}]},
                    config={"callbacks": callbacks, "recursion_limit": 32},
                )
            structured = state.get("structured_response")
            if isinstance(structured, BriefingResearchResult):
                payload = structured.model_dump(mode="json")
            elif isinstance(structured, dict):
                payload = cast("dict[str, Any]", structured)
            else:
                msg = "Deep Agent returned no structured response"
                raise InvalidEnrichmentError(msg)
            budget.check_complete()
            if len(json.dumps(payload).encode()) > _MAX_OUTPUT_BYTES:
                msg = "Research output budget exhausted"
                raise ResearchBudgetError(msg)
            return payload, set(budget.fetched_urls)
        except OpenAIError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    msg = "AI provider is not configured"
    raise RuntimeError(msg)


def _failure_code(exc: BaseException) -> str:
    from openai import OpenAIError

    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ResearchBudgetError):
            return "budget_exhausted"
        if isinstance(current, InvalidEnrichmentError):
            return "invalid_output"
        if isinstance(current, TimeoutError):
            return "research_timeout"
        if isinstance(current, httpx.HTTPError):
            return "browsing_failed"
        if isinstance(current, OpenAIError):
            return "provider_failed"
        current = current.__cause__ or current.__context__
    return "research_failed"


def enrich_briefing_for_email(  # noqa: PLR0911 - explicit fail-open outcomes
    briefing: Mapping[str, Any],
    *,
    user_id: int,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Return cached or newly researched enrichment; fail open to canonical email."""
    briefing_id = int(briefing["id"])
    cached = load_completed_enrichment(user_id, briefing_id, database_url=database_url)
    if cached is not None:
        return cached
    tavily_api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not tavily_api_key:
        _record_skipped(
            user_id,
            briefing_id,
            "web_search_not_configured",
            database_url=database_url,
        )
        return None
    if not _model_configs():
        _record_skipped(
            user_id,
            briefing_id,
            "ai_not_configured",
            database_url=database_url,
        )
        return None
    sections = select_research_sections(briefing)
    if not sections:
        _record_skipped(
            user_id,
            briefing_id,
            "no_sourced_sections",
            database_url=database_url,
        )
        return None
    if not _claim_run(user_id, briefing_id, database_url=database_url):
        return load_completed_enrichment(user_id, briefing_id, database_url=database_url)
    try:
        payload, fetched_urls = _invoke_deep_research(
            sections,
            _personalization_context(user_id, database_url=database_url),
            user_id=user_id,
            briefing_id=briefing_id,
        )
        validated = validate_research_result(
            briefing,
            payload,
            fetched_urls=fetched_urls,
        )
        model = (
            os.getenv("OPENAI_BRIEFING_ENRICHMENT_MODEL")
            or os.getenv("OPENAI_BRIEFING_MODEL")
            or "gpt-4o-mini"
        )
        save_completed_enrichment(
            user_id=user_id,
            briefing_id=briefing_id,
            content=validated,
            model=model,
            database_url=database_url,
        )
        return validated
    except Exception as exc:
        _record_failure(
            user_id,
            briefing_id,
            _failure_code(exc),
            database_url=database_url,
        )
        logger.warning(
            "Briefing email enrichment failed user_id=%s briefing_id=%s",
            user_id,
            briefing_id,
        )
        return None
