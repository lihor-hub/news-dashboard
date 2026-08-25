"""Tests for bounded deep-research enrichment of briefing emails."""

from __future__ import annotations

from typing import Any

import pytest

from news_dashboard.auth import create_user
from news_dashboard.briefing_email.enrichment import (
    InvalidEnrichmentError,
    ResearchBudgetError,
    _personalization_context,
    _ResearchBudget,
    enrich_briefing_for_email,
    load_completed_enrichment,
    save_completed_enrichment,
    select_research_sections,
    validate_research_result,
)
from news_dashboard.db import connect


def _briefing(section_count: int = 7) -> dict[str, Any]:
    articles = [
        {
            "id": index,
            "title": f"Article {index}",
            "url": f"https://example.com/{index}",
            "source_name": f"Source {index}",
            "summary": f"Article summary {index}",
        }
        for index in range(1, section_count + 1)
    ]
    return {
        "id": 41,
        "title": "Daily briefing",
        "summary": "What matters today",
        "content": {
            "sections": [
                {
                    "title": f"Section {index}",
                    "body": f"Section body {index}",
                    "citations": [index],
                }
                for index in range(1, section_count + 1)
            ]
        },
        "articles": articles,
    }


def test_select_research_sections_uses_first_five_canonical_sections() -> None:
    selected = select_research_sections(_briefing())

    assert [section.section_index for section in selected] == [0, 1, 2, 3, 4]
    assert [section.title for section in selected] == [f"Section {index}" for index in range(1, 6)]
    assert selected[0].sources[0].article_id == 1
    assert selected[0].sources[0].url == "https://example.com/1"


def test_select_research_sections_never_invents_missing_sections() -> None:
    selected = select_research_sections(_briefing(section_count=2))

    assert len(selected) == 2


def test_select_research_sections_ignores_sections_without_cited_sources() -> None:
    briefing = _briefing(section_count=3)
    briefing["content"]["sections"][0]["citations"] = [999]

    selected = select_research_sections(briefing)

    assert [section.title for section in selected] == ["Section 2", "Section 3"]


@pytest.mark.postgres
def test_enrichment_is_disabled_with_inspectable_status(
    pg_clean: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = int(create_user("deep_research_disabled", "password123", db_path=pg_clean)["id"])
    briefing = _briefing(section_count=1)
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(user_id, since_at, until_at, status, title, summary, content)
            VALUES (%s, NOW() - INTERVAL '1 day', NOW(), 'complete', 'Daily', 'Summary',
                    '{"sections":[]}'::jsonb)
            RETURNING id
            """,
            (user_id,),
        ).fetchone()
    assert row is not None
    briefing["id"] = int(row["id"])
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    assert enrich_briefing_for_email(briefing, user_id=user_id, database_url=pg_clean) is None
    with connect(database_url=pg_clean) as conn:
        status = conn.execute(
            "SELECT status, error_code FROM briefing_email_enrichments WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    assert status is not None
    assert status["status"] == "skipped"
    assert status["error_code"] == "web_search_not_configured"


@pytest.mark.postgres
def test_completed_enrichment_is_reused_only_by_its_owner(pg_clean: str) -> None:
    owner_id = int(create_user("enrichment_owner", "password123", db_path=pg_clean)["id"])
    other_id = int(create_user("enrichment_other", "password123", db_path=pg_clean)["id"])
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(user_id, since_at, until_at, status, title, summary, content)
            VALUES (%s, NOW() - INTERVAL '1 day', NOW(), 'complete', 'Daily', 'Summary',
                    '{"sections":[]}'::jsonb)
            RETURNING id
            """,
            (owner_id,),
        ).fetchone()
    assert row is not None
    briefing_id = int(row["id"])
    content = {"sections": [{"section_index": 0, "context": "External context"}]}

    save_completed_enrichment(
        user_id=owner_id,
        briefing_id=briefing_id,
        content=content,
        model="research-model",
        database_url=pg_clean,
    )

    assert load_completed_enrichment(owner_id, briefing_id, database_url=pg_clean) == content
    assert load_completed_enrichment(other_id, briefing_id, database_url=pg_clean) is None


@pytest.mark.postgres
def test_personalization_uses_configured_interests_and_source_subscriptions(pg_clean: str) -> None:
    user_id = int(create_user("research_personalization", "password123", db_path=pg_clean)["id"])
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO user_interest_profiles(user_id, interests) VALUES (%s, %s::jsonb)",
            (user_id, '["agents", "python"]'),
        )
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, enabled)
            VALUES ('research-enabled', 'Research Enabled', 'https://enabled.example/feed',
                    'ai-llm', 'rss', TRUE),
                   ('research-disabled', 'Research Disabled', 'https://disabled.example/feed',
                    'ai-llm', 'rss', TRUE)
            """
        )
        conn.execute(
            """
            INSERT INTO user_sources(user_id, source_slug, enabled)
            VALUES (%s, 'research-enabled', TRUE), (%s, 'research-disabled', FALSE)
            """,
            (user_id, user_id),
        )

    context = _personalization_context(user_id, database_url=pg_clean)

    assert context["interests"] == ["agents", "python"]
    assert "Research Enabled" in context["subscribed_sources"]
    assert "Research Disabled" not in context["subscribed_sources"]


def test_validate_research_result_rejects_unsafe_external_citation() -> None:
    payload = {
        "sections": [
            {
                "section_index": 0,
                "key_takeaways": ["Takeaway"],
                "context": "Context",
                "evidence_status": "uncertain",
                "evidence_summary": "Evidence summary",
                "related_information": "Related information",
                "why_it_matters": "Relevant to configured interests",
                "citations": [
                    {
                        "title": "Unsafe source",
                        "publisher": "Unknown",
                        "url": "http://127.0.0.1/private",
                    }
                ],
            }
        ]
    }

    with pytest.raises(InvalidEnrichmentError, match="citation"):
        validate_research_result(_briefing(), payload)


def test_validate_research_result_accepts_bounded_cited_section() -> None:
    payload = {
        "sections": [
            {
                "section_index": 0,
                "key_takeaways": ["Takeaway one", "Takeaway two"],
                "context": "External context",
                "evidence_status": "corroborated",
                "evidence_summary": "Independent reporting supports the claim.",
                "related_information": "Related release",
                "why_it_matters": "Relevant to your agents interest.",
                "citations": [
                    {
                        "title": "Independent source",
                        "publisher": "Research publisher",
                        "url": "https://research.example/evidence",
                    }
                ],
            }
        ]
    }

    validated = validate_research_result(_briefing(section_count=1), payload)

    assert validated["sections"][0]["evidence_status"] == "corroborated"
    assert validated["sections"][0]["citations"][0]["url"] == ("https://research.example/evidence")


def test_validate_research_result_rejects_citation_not_fetched_by_tool() -> None:
    payload = {
        "sections": [
            {
                "section_index": 0,
                "key_takeaways": ["Takeaway"],
                "context": "Context",
                "evidence_status": "uncertain",
                "evidence_summary": "Evidence",
                "related_information": "Related",
                "why_it_matters": "Relevant",
                "citations": [
                    {
                        "title": "Unfetched",
                        "publisher": "Research",
                        "url": "https://research.example/unfetched",
                    }
                ],
            }
        ]
    }

    with pytest.raises(InvalidEnrichmentError, match="unverified citation"):
        validate_research_result(_briefing(section_count=1), payload, fetched_urls=set())


def test_validate_research_result_requires_every_selected_section() -> None:
    payload = {
        "sections": [
            {
                "section_index": 0,
                "key_takeaways": ["Takeaway"],
                "context": "Context",
                "evidence_status": "mixed",
                "evidence_summary": "Mixed evidence",
                "related_information": "Related",
                "why_it_matters": "Relevant",
                "citations": [
                    {
                        "title": "Independent",
                        "publisher": "Research",
                        "url": "https://research.example/report",
                    }
                ],
            }
        ]
    }

    with pytest.raises(InvalidEnrichmentError, match="every selected section"):
        validate_research_result(_briefing(section_count=2), payload)


@pytest.mark.postgres
def test_enrich_briefing_persists_and_reuses_deep_agent_result(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = int(create_user("deep_research_owner", "password123", db_path=pg_clean)["id"])
    briefing = _briefing(section_count=1)
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(user_id, since_at, until_at, status, title, summary, content)
            VALUES (%s, NOW() - INTERVAL '1 day', NOW(), 'complete', 'Daily', 'Summary',
                    %s::jsonb)
            RETURNING id
            """,
            (user_id, '{"sections":[]}'),
        ).fetchone()
    assert row is not None
    briefing["id"] = int(row["id"])
    monkeypatch.setenv("TAVILY_API_KEY", "configured")
    monkeypatch.setenv("OPENAI_API_KEY", "configured")
    calls = 0

    def fake_invoke(*_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], set[str]]:
        nonlocal calls
        calls += 1
        payload = {
            "sections": [
                {
                    "section_index": 0,
                    "key_takeaways": ["Takeaway"],
                    "context": "Context",
                    "evidence_status": "corroborated",
                    "evidence_summary": "Independent support",
                    "related_information": "Related",
                    "why_it_matters": "Matches configured interests",
                    "citations": [
                        {
                            "title": "Independent",
                            "publisher": "Research",
                            "url": "https://research.example/report",
                        }
                    ],
                }
            ]
        }
        return payload, {"https://research.example/report"}

    monkeypatch.setattr(
        "news_dashboard.briefing_email.enrichment._invoke_deep_research", fake_invoke
    )

    first = enrich_briefing_for_email(briefing, user_id=user_id, database_url=pg_clean)
    second = enrich_briefing_for_email(briefing, user_id=user_id, database_url=pg_clean)

    assert first == second
    assert calls == 1


@pytest.mark.postgres
def test_enrich_briefing_returns_none_and_records_failure(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    user_id = int(create_user("deep_research_failure", "password123", db_path=pg_clean)["id"])
    briefing = _briefing(section_count=1)
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(user_id, since_at, until_at, status, title, summary, content)
            VALUES (%s, NOW() - INTERVAL '1 day', NOW(), 'complete', 'Daily', 'Summary',
                    %s::jsonb)
            RETURNING id
            """,
            (user_id, '{"sections":[]}'),
        ).fetchone()
    assert row is not None
    briefing["id"] = int(row["id"])
    monkeypatch.setenv("TAVILY_API_KEY", "configured")
    monkeypatch.setenv("OPENAI_API_KEY", "configured")

    def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        msg = "secret provider payload"
        raise TimeoutError(msg)

    monkeypatch.setattr("news_dashboard.briefing_email.enrichment._invoke_deep_research", fail)

    assert enrich_briefing_for_email(briefing, user_id=user_id, database_url=pg_clean) is None
    with connect(database_url=pg_clean) as conn:
        status = conn.execute(
            "SELECT status, error_code FROM briefing_email_enrichments WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    assert status is not None
    assert status["status"] == "failed"
    assert status["error_code"] == "research_timeout"
    assert "secret provider payload" not in caplog.text


def test_research_budget_enforces_model_and_runtime_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    budget = _ResearchBudget(model_calls=16)
    with pytest.raises(ResearchBudgetError, match="Model-call"):
        budget.claim_model()

    search_budget = _ResearchBudget(searches=8)
    with pytest.raises(ResearchBudgetError, match="search"):
        search_budget.claim_search()

    page_budget = _ResearchBudget(page_fetches=12)
    with pytest.raises(ResearchBudgetError, match="page"):
        page_budget.claim_page()

    monkeypatch.setattr("news_dashboard.briefing_email.enrichment.time.monotonic", lambda: 10.0)
    expired = _ResearchBudget(deadline=9.0)
    with pytest.raises(ResearchBudgetError, match="runtime"):
        expired.claim_search()
