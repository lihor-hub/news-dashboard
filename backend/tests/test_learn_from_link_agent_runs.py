"""Tests for Learn from Link run/step trace bookkeeping (issue #1131)."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.callbacks import BaseCallbackHandler

from news_dashboard.db import connect
from news_dashboard.learn_from_link import agent_runs, service
from news_dashboard.learn_from_link.agent_runs import (
    STEP_CITATION_VERIFICATION,
    STEP_EXTRACTION,
    STEP_FETCH,
    STEP_PERSISTENCE,
    STEP_SYNTHESIS,
    SYNTHESIS_PROMPT_VERSION,
)


def _run_row(database_url: str, lesson_id: int) -> dict[str, Any]:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "SELECT * FROM learning_agent_runs WHERE lesson_id = %s ORDER BY id DESC LIMIT 1",
            (lesson_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def _step_rows(database_url: str, run_id: int) -> list[dict[str, Any]]:
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            "SELECT * FROM learning_agent_steps WHERE run_id = %s ORDER BY ordinal",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _make_user(database_url: str, username: str = "alice") -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


@pytest.fixture(autouse=True)
def _lesson_extraction_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service,
        "fetch_url_metadata",
        lambda url: {
            "title": f"Title for {url}",
            "site_name": "Example Source",
            "author": "Example Author",
            "published_at": "2026-07-09",
        },
        raising=False,
    )
    monkeypatch.setattr(
        service,
        "extract_body",
        lambda url: (f"Body for {url}", "ok"),
        raising=False,
    )


def test_successful_generation_records_version_metadata_and_all_steps(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    lesson = service.create_lesson(
        user_id, "https://example.com/a", depth="deep", persona="new_to_ai", database_url=pg_clean
    )

    run = _run_row(pg_clean, int(lesson["id"]))
    assert run["status"] == "complete"
    assert run["prompt_version"] == SYNTHESIS_PROMPT_VERSION
    assert run["model_version"]
    assert run["config"] == {"depth": "deep", "persona": "new_to_ai"}
    assert run["failed_step"] is None
    assert run["error"] is None
    assert run["total_latency_ms"] is not None

    steps = _step_rows(pg_clean, int(run["id"]))
    assert [s["step"] for s in steps] == [
        STEP_FETCH,
        STEP_EXTRACTION,
        STEP_SYNTHESIS,
        STEP_CITATION_VERIFICATION,
        STEP_PERSISTENCE,
    ]
    assert all(s["status"] == "complete" for s in steps)
    assert all(s["latency_ms"] is not None for s in steps)


def test_lesson_graph_is_compiled_without_a_checkpointer() -> None:
    graph = service.build_lesson_graph()
    drawable = graph.get_graph()

    assert graph.checkpointer is None
    assert set(drawable.nodes) == {
        "__start__",
        "fetch",
        "extraction",
        "synthesis",
        "citation_verification",
        "personal_relevance",
        "persistence",
        "failure",
        "__end__",
    }
    assert [(edge.source, edge.target, edge.data, edge.conditional) for edge in drawable.edges] == [
        ("__start__", "fetch", None, False),
        ("citation_verification", "failure", "fail", True),
        ("citation_verification", "personal_relevance", "continue", True),
        ("extraction", "failure", "fail", True),
        ("extraction", "synthesis", "continue", True),
        ("fetch", "extraction", None, False),
        ("personal_relevance", "persistence", None, False),
        ("synthesis", "citation_verification", "continue", True),
        ("synthesis", "failure", "fail", True),
        ("failure", "__end__", None, False),
        ("persistence", "__end__", None, False),
    ]


def test_generation_propagates_user_session_and_native_callback(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "test-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-secret")
    user_id = _make_user(pg_clean)
    callback = BaseCallbackHandler()
    propagated: dict[str, Any] = {}

    @contextmanager
    def attributes(**kwargs: Any) -> Generator[None]:
        propagated.update(kwargs)
        yield

    with (
        patch("langfuse.propagate_attributes", side_effect=attributes),
        patch("langfuse.langchain.CallbackHandler", return_value=callback) as handler,
    ):
        lesson = service.create_lesson(user_id, "https://example.com/traced", database_url=pg_clean)

    run = _run_row(pg_clean, int(lesson["id"]))
    handler.assert_called_once_with()
    assert propagated == {
        "user_id": str(user_id),
        "session_id": f"lesson-run:{run['id']}",
        "tags": ["lesson", "generation"],
        "trace_name": "lesson-generation",
    }


def test_extraction_failure_marks_run_failed_at_extraction_step(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    monkeypatch.setattr(service, "extract_body", lambda _url: ("", "error"), raising=False)

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    run = _run_row(pg_clean, int(lesson["id"]))
    assert run["status"] == "failed"
    assert run["failed_step"] == STEP_EXTRACTION
    assert run["error"] == "Could not extract readable article content."

    steps = _step_rows(pg_clean, int(run["id"]))
    assert [(step["step"], step["ordinal"], step["status"], step["error"]) for step in steps] == [
        (STEP_FETCH, 1, "complete", None),
        (STEP_EXTRACTION, 2, "failed", "extract_body returned status='error'"),
    ]


def test_citation_failure_marks_run_failed_at_citation_verification_step(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    monkeypatch.setattr(
        service,
        "generate_structured_lesson_detail",
        lambda _fields, **_kwargs: {
            "gist": "A gist grounded in the article.",
            "explanation": "A short explanation grounded in the article.",
            "key_claims": ["A grounded claim."],
            "prerequisite_concepts": ["Background context"],
            "why_it_matters": "It matters because the source is useful.",
            "read_worthiness": {"verdict": "read", "rationale": "The source is useful."},
            "who_should_read": ["Curious readers"],
            "questions_to_keep_in_mind": ["Which claims are supported?"],
            "citations": [
                {
                    "label": "1",
                    "snippet": "This invented quote is absent from the article.",
                    "source": "Metadata title",
                }
            ],
        },
        raising=False,
    )

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    run = _run_row(pg_clean, int(lesson["id"]))
    assert run["status"] == "failed"
    assert run["failed_step"] == STEP_CITATION_VERIFICATION
    assert run["error"] == "Generated lesson citations did not match source content."

    steps = _step_rows(pg_clean, int(run["id"]))
    assert [(step["step"], step["ordinal"], step["status"], step["error"]) for step in steps] == [
        (STEP_FETCH, 1, "complete", None),
        (STEP_EXTRACTION, 2, "complete", None),
        (STEP_SYNTHESIS, 3, "complete", None),
        (
            STEP_CITATION_VERIFICATION,
            4,
            "failed",
            "Generated lesson citations did not match source content.",
        ),
    ]


def test_synthesis_failure_marks_run_failed_at_synthesis_step(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    monkeypatch.setattr(
        service,
        "generate_structured_lesson_detail",
        lambda _fields, **_kwargs: {"gist": "Only one field is not enough."},
        raising=False,
    )

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    run = _run_row(pg_clean, int(lesson["id"]))
    assert run["status"] == "failed"
    assert run["failed_step"] == STEP_SYNTHESIS
    assert run["error"] == "Generated lesson detail was malformed."

    steps = _step_rows(pg_clean, int(run["id"]))
    assert [(step["step"], step["ordinal"], step["status"], step["error"]) for step in steps] == [
        (STEP_FETCH, 1, "complete", None),
        (STEP_EXTRACTION, 2, "complete", None),
        (STEP_SYNTHESIS, 3, "failed", "Generated lesson detail was malformed."),
    ]


def test_admin_run_summary_returns_recent_runs_with_steps(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    summary = agent_runs.admin_run_summary(database_url=pg_clean)

    assert len(summary["items"]) == 1
    item = summary["items"][0]
    assert item["status"] == "complete"
    assert len(item["steps"]) == 5
    assert item["steps"][0]["step"] == STEP_FETCH
