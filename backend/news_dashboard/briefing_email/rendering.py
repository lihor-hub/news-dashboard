"""Pure Jinja rendering for canonical daily briefings."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, cast
from urllib.parse import urlparse

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from news_dashboard.email_theme import (
    EMAIL_COLORS,
    FONT_SERIF,
    compact_text,
    render_email_shell,
)

_WORDS_PER_MINUTE = 200
_ENVIRONMENT = Environment(
    loader=PackageLoader("news_dashboard.briefing_email", "templates"),
    autoescape=select_autoescape(enabled_extensions=("html.j2",)),
    undefined=StrictUndefined,
)


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    """Rendered multipart content and its estimated reading duration."""

    subject: str
    html_body: str
    text_body: str
    estimated_minutes: int


def _safe_link(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value.strip())
        hostname = parsed.hostname
        _port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        return None
    return parsed.geturl()


def _as_mapping(value: object) -> Mapping[str, Any]:
    return cast("Mapping[str, Any]", value) if isinstance(value, Mapping) else {}


def _as_mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast("Mapping[str, Any]", item) for item in value if isinstance(item, Mapping)]


def render_briefing_email(
    briefing: Mapping[str, Any],
    *,
    enrichment: Mapping[str, Any] | None = None,
    local_date: date,
    timezone_name: str,
    briefing_url: str,
    preferences_url: str,
    unsubscribe_url: str,
) -> RenderedEmail:
    """Render one saved briefing without performing I/O."""
    content = _as_mapping(briefing.get("content"))
    sections = _as_mappings(content.get("sections"))
    articles = _as_mappings(briefing.get("articles"))
    articles_by_id = {article.get("id"): article for article in articles}
    enrichment_rows = _as_mappings((enrichment or {}).get("sections"))
    enrichments_by_index = {
        item.get("section_index"): item
        for item in enrichment_rows
        if isinstance(item.get("section_index"), int)
    }

    stories: list[dict[str, Any]] = []
    words: list[str] = [str(briefing.get("summary") or "")]
    for section_index, section in enumerate(sections):
        citations = section.get("citations")
        cited_articles = []
        if isinstance(citations, list):
            for article_id in citations:
                article = articles_by_id.get(article_id)
                if article is not None:
                    cited_articles.append(
                        {
                            "title": compact_text(article.get("title"), fallback="Source"),
                            "source_name": str(article.get("source_name") or ""),
                            "url": _safe_link(article.get("url")),
                        }
                    )
        title = str(section.get("title") or "")
        body = str(section.get("body") or "")
        research = enrichments_by_index.get(section_index)
        rendered_research: dict[str, Any] | None = None
        if research is not None:
            citation_rows = _as_mappings(research.get("citations"))
            external_citations = [
                {
                    "title": compact_text(item.get("title"), fallback="External source"),
                    "publisher": compact_text(item.get("publisher"), fallback=""),
                    "url": _safe_link(item.get("url")),
                }
                for item in citation_rows
                if _safe_link(item.get("url")) is not None
            ]
            takeaways_value = research.get("key_takeaways")
            takeaways = (
                [str(item) for item in takeaways_value if isinstance(item, str)]
                if isinstance(takeaways_value, list)
                else []
            )
            if external_citations:
                rendered_research = {
                    "key_takeaways": takeaways,
                    "context": str(research.get("context") or ""),
                    "evidence_status": str(research.get("evidence_status") or "uncertain"),
                    "evidence_summary": str(research.get("evidence_summary") or ""),
                    "related_information": str(research.get("related_information") or ""),
                    "why_it_matters": str(research.get("why_it_matters") or ""),
                    "citations": external_citations,
                }
                words.extend(
                    [
                        *takeaways,
                        rendered_research["context"],
                        rendered_research["evidence_summary"],
                        rendered_research["related_information"],
                        rendered_research["why_it_matters"],
                    ]
                )
        stories.append(
            {
                "title": title,
                "body": body,
                "articles": cited_articles,
                "research": rendered_research,
            }
        )
        words.extend((title, body))

    estimated_minutes = max(1, math.ceil(len(" ".join(words).split()) / _WORDS_PER_MINUTE))
    context = {
        "title": str(briefing.get("title") or "Daily briefing"),
        "summary": str(briefing.get("summary") or ""),
        "stories": stories,
        "local_date": local_date.strftime("%B %-d, %Y"),
        "timezone_name": timezone_name,
        "estimated_minutes": estimated_minutes,
        "briefing_url": _safe_link(briefing_url),
        "preferences_url": _safe_link(preferences_url),
        "unsubscribe_url": _safe_link(unsubscribe_url),
        "colors": {name: color.email_hex for name, color in EMAIL_COLORS.items()},
        "font_serif": FONT_SERIF,
    }
    body_html = _ENVIRONMENT.get_template("briefing.html.j2").render(context)
    return RenderedEmail(
        subject=f"Daily briefing: {context['title']}",
        html_body=render_email_shell(
            preheader=str(context["summary"]),
            eyebrow="Current-day report",
            heading=str(context["title"]),
            body_html=body_html,
        ),
        text_body=_ENVIRONMENT.get_template("briefing.txt.j2").render(context),
        estimated_minutes=estimated_minutes,
    )
