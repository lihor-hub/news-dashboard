"""Tests for the Learn from Link lesson synthesis eval set (issue #1131)."""

from __future__ import annotations

from typing import Any

from news_dashboard.db import connect
from news_dashboard.learn_from_link.evals import (
    FEATURE,
    LESSON_EVAL_FIXTURES,
    run_lesson_evals,
    score_lesson_fixture,
    seed_lesson_eval_examples,
)


def _fixture(name: str) -> dict[str, Any]:
    return next(f for f in LESSON_EVAL_FIXTURES if f["name"] == name)


def test_good_lesson_fixture_passes() -> None:
    passed, score, reason = score_lesson_fixture(_fixture("good-lesson"))
    assert passed is True
    assert score == 1.0
    assert reason is None


def test_insufficient_source_fixture_passes_with_skim_verdict() -> None:
    passed, score, reason = score_lesson_fixture(_fixture("insufficient-source"))
    assert passed is True
    assert score == 1.0
    assert reason is None


def test_bad_citation_fixture_passes_because_validation_correctly_rejects_it() -> None:
    passed, score, reason = score_lesson_fixture(_fixture("bad-citation"))
    assert passed is True
    assert score == 1.0
    assert reason is None


def test_score_lesson_fixture_fails_when_validation_unexpectedly_rejects_a_good_case() -> None:
    fixture = dict(_fixture("good-lesson"))
    fixture["expected"] = {**fixture["expected"], "min_key_claims": 99}
    passed, score, reason = score_lesson_fixture(fixture)
    assert passed is False
    assert score == 0.0
    assert reason is not None
    assert "too few key claims" in reason


def test_score_lesson_fixture_fails_when_a_bad_case_unexpectedly_validates() -> None:
    fixture = dict(_fixture("bad-citation"))
    fixture["expected"] = {"expect_valid": True, "min_key_claims": 1}
    passed, _score, reason = score_lesson_fixture(fixture)
    assert passed is False
    assert reason is not None


def test_seed_lesson_eval_examples_is_idempotent(pg_clean: str) -> None:
    first_ids = seed_lesson_eval_examples(database_url=pg_clean)
    second_ids = seed_lesson_eval_examples(database_url=pg_clean)

    assert first_ids == second_ids
    with connect(database_url=pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_eval_examples WHERE feature = %s", (FEATURE,)
        ).fetchone()["count"]
    assert count == len(LESSON_EVAL_FIXTURES)


def test_run_lesson_evals_persists_a_passing_run(pg_clean: str) -> None:
    result = run_lesson_evals(database_url=pg_clean)

    assert result["total"] == len(LESSON_EVAL_FIXTURES)
    assert result["failed"] == 0
    assert result["passed"] == len(LESSON_EVAL_FIXTURES)

    with connect(database_url=pg_clean) as conn:
        run_row = conn.execute(
            "SELECT status FROM ai_eval_runs WHERE id = %s", (result["run_id"],)
        ).fetchone()
        result_count = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_eval_results WHERE run_id = %s", (result["run_id"],)
        ).fetchone()["count"]
    assert run_row["status"] == "passed"
    assert result_count == len(LESSON_EVAL_FIXTURES)
