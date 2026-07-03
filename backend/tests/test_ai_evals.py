from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from news_dashboard.ai_evals import admin_quality_summary, run_local_evals, score_output
from news_dashboard.cli import app
from news_dashboard.db import connect


def test_score_output_rejects_unknown_citation() -> None:
    passed, score, reason = score_output(
        {"answer": "See this.", "citations": [9]},
        {"allowed_citation_ids": [1, 2], "requires_citation": True},
    )

    assert passed is False
    assert score == 0.0
    assert reason == "unknown citations"


def test_run_local_evals_records_pass_and_failure(pg_clean: str) -> None:
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO ai_eval_examples(feature, input, expected_properties)
            VALUES
              ('ask-ai', %s::jsonb, %s::jsonb),
              ('briefing-generation', %s::jsonb, %s::jsonb)
            """,
            (
                json.dumps({"fake_output": {"answer": "insufficient context", "citations": []}}),
                json.dumps({"weak_retrieval": True}),
                json.dumps({"fake_output": {"sections": [{"citations": [2]}]}}),
                json.dumps({"briefing": True, "allowed_citation_ids": [1]}),
            ),
        )

    result = run_local_evals(database_url=pg_clean)

    assert result["total"] == 2
    assert result["passed"] == 1
    assert result["failed"] == 1
    summary = admin_quality_summary(database_url=pg_clean)
    assert summary["evals"][0]["failed"] == 1
    assert summary["recent_failures"][0]["failure_reason"] == "unknown briefing citations"


def test_eval_ai_cli_exits_nonzero_on_failed_eval(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO ai_eval_examples(feature, input, expected_properties)
            VALUES ('ask-ai', %s::jsonb, %s::jsonb)
            """,
            (
                json.dumps({"fake_output": {"answer": "too long", "citations": []}}),
                json.dumps({"max_chars": 2}),
            ),
        )

    result = CliRunner().invoke(app, ["eval-ai"])

    assert result.exit_code == 1
    assert "0/1 passed, 1 failed" in result.output
