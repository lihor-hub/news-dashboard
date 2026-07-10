"""Small eval set for Learn from Link lesson synthesis quality.

Models the persistence/scoring pattern in ``news_dashboard.ai_evals``
(``ai_eval_examples`` / ``ai_eval_runs`` / ``ai_eval_results``), but scores the
lesson-specific structured contract (``LessonDetail`` + citation grounding)
instead of the generic answer/citations shape used for ask-ai/briefing evals.

Covers three cases required by issue #1131: a well-grounded lesson, a lesson
whose citations don't match the source (must be rejected), and a lesson built
from an unusually short/insufficient source (must degrade gracefully, not
crash or silently overclaim).
"""

from __future__ import annotations

import json
from typing import Any

from news_dashboard.db import connect, init_db
from news_dashboard.learn_from_link.agent_runs import SYNTHESIS_PROMPT_VERSION
from news_dashboard.learn_from_link.service import (
    DEFAULT_LESSON_CHAT_MODEL,
    LessonCitationValidationError,
    LessonDetailValidationError,
    generate_structured_lesson_detail,
    validate_structured_lesson_detail,
    verify_lesson_citations,
)

FEATURE = "lesson-synthesis"

_VERDICT_RANK = {"skip": 0, "skim": 1, "read": 2, "study": 3}

LESSON_EVAL_FIXTURES: list[dict[str, Any]] = [
    {
        "name": "good-lesson",
        "lesson_fields": {
            "title": "Understanding Rate Limiters",
            "original_url": "https://example.com/rate-limiters",
            "source_name": "Example Engineering Blog",
            "author": "Ada Engineer",
            "published_at": "2026-01-05",
            "source_content": (
                "Rate limiters protect services from overload by capping request "
                "throughput. The token bucket algorithm refills tokens at a fixed "
                "rate and rejects requests once the bucket is empty, which allows "
                "short bursts while still bounding sustained throughput over time. "
                "Sliding window counters trade memory for smoother enforcement than "
                "fixed windows, avoiding the burst-at-boundary problem that simple "
                "fixed windows suffer from. Leaky bucket queues excess requests and "
                "drains them at a constant rate instead of rejecting them outright. "
                "Choosing an algorithm depends on burst tolerance, fairness "
                "requirements, and implementation complexity across a distributed "
                "fleet of servers that must agree on shared counters."
            ),
        },
        "depth": "normal",
        "persona": "developer",
        "expected": {"min_key_claims": 3, "min_verdict": "read", "expect_valid": True},
    },
    {
        "name": "insufficient-source",
        "lesson_fields": {
            "title": "Short Note",
            "original_url": "https://example.com/short-note",
            "source_name": "Example Blog",
            "author": None,
            "published_at": None,
            "source_content": "A brief announcement with little substance.",
        },
        "depth": "normal",
        "persona": "developer",
        "expected": {"verdict": "skim", "expect_valid": True},
    },
    {
        "name": "bad-citation",
        "lesson_fields": {
            "title": "Grounded Article",
            "original_url": "https://example.com/grounded",
            "source_name": "Example Journal",
            "author": "Ada Writer",
            "published_at": "2026-02-01",
            "source_content": "This article explains how caches evict entries using LRU.",
        },
        "depth": "normal",
        "persona": "developer",
        "expected": {"expect_valid": False},
        # A deliberately-fabricated synthesis payload simulating a hallucinated
        # citation that never appears in the source, to exercise the citation
        # verification failure path end to end.
        "fake_raw_detail": {
            "gist": "Caches use LRU eviction.",
            "explanation": "This article explains how caches evict entries using LRU.",
            "key_claims": ["Caches use LRU eviction."],
            "prerequisite_concepts": ["Cache basics"],
            "why_it_matters": "It matters for developers weighing implementation details.",
            "read_worthiness": {"verdict": "read", "rationale": "Useful background."},
            "who_should_read": ["Developers"],
            "questions_to_keep_in_mind": ["What evicts first?"],
            "citations": [
                {
                    "label": "1",
                    "snippet": "This invented quote never appears in the source.",
                    "source": "Grounded Article",
                }
            ],
        },
    },
]


def score_lesson_fixture(fixture: dict[str, Any]) -> tuple[bool, float, str | None]:
    """Run one fixture through the real synthesis + validation pipeline and score it."""
    lesson_fields = fixture["lesson_fields"]
    expected = fixture["expected"]
    try:
        raw_detail = fixture.get("fake_raw_detail") or generate_structured_lesson_detail(
            lesson_fields, depth=fixture["depth"], persona=fixture["persona"]
        )
        detail = validate_structured_lesson_detail(raw_detail)
        verify_lesson_citations(detail, lesson_fields)
    except (LessonDetailValidationError, LessonCitationValidationError) as exc:
        if expected.get("expect_valid", True) is False:
            return True, 1.0, None
        return False, 0.0, f"unexpected validation failure: {exc}"

    if expected.get("expect_valid") is False:
        return False, 0.0, "expected validation to fail but it passed"

    failures: list[str] = []
    min_key_claims = expected.get("min_key_claims")
    if min_key_claims is not None and len(detail.key_claims) < min_key_claims:
        failures.append("too few key claims")
    verdict = expected.get("verdict")
    if verdict is not None and detail.read_worthiness.verdict != verdict:
        failures.append(f"expected verdict {verdict!r}, got {detail.read_worthiness.verdict!r}")
    min_verdict = expected.get("min_verdict")
    if (
        min_verdict is not None
        and _VERDICT_RANK[detail.read_worthiness.verdict] < _VERDICT_RANK[min_verdict]
    ):
        failures.append(f"verdict {detail.read_worthiness.verdict!r} below minimum {min_verdict!r}")
    passed = not failures
    return passed, 1.0 if passed else 0.0, "; ".join(failures) or None


def seed_lesson_eval_examples(*, database_url: str | None = None) -> list[int]:
    """Insert the fixture set into ai_eval_examples if not already present, return ids."""
    init_db(database_url=database_url)
    ids: list[int] = []
    with connect(database_url=database_url) as conn:
        for fixture in LESSON_EVAL_FIXTURES:
            existing = conn.execute(
                "SELECT id FROM ai_eval_examples WHERE feature = %s AND input->>'name' = %s",
                (FEATURE, fixture["name"]),
            ).fetchone()
            if existing is not None:
                ids.append(int(existing["id"]))
                continue
            row = conn.execute(
                """
                INSERT INTO ai_eval_examples
                  (feature, prompt_version, model_version, input, expected_properties)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
                RETURNING id
                """,
                (
                    FEATURE,
                    SYNTHESIS_PROMPT_VERSION,
                    DEFAULT_LESSON_CHAT_MODEL,
                    json.dumps(fixture),
                    json.dumps(fixture["expected"]),
                ),
            ).fetchone()
            if row is not None:
                ids.append(int(row["id"]))
    return ids


def run_lesson_evals(*, database_url: str | None = None) -> dict[str, Any]:
    """Seed (if needed) and score the lesson eval fixture set, persisting a run."""
    init_db(database_url=database_url)
    seed_lesson_eval_examples(database_url=database_url)
    with connect(database_url=database_url) as conn:
        run = conn.execute(
            """
            INSERT INTO ai_eval_runs(feature, prompt_version, model_version)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (FEATURE, SYNTHESIS_PROMPT_VERSION, DEFAULT_LESSON_CHAT_MODEL),
        ).fetchone()
        if run is None:
            msg = "INSERT INTO ai_eval_runs returned no row"
            raise RuntimeError(msg)
        run_id = int(run["id"])
        examples = conn.execute(
            "SELECT id, input FROM ai_eval_examples WHERE feature = %s ORDER BY id",
            (FEATURE,),
        ).fetchall()
        passed_count = 0
        for example in examples:
            fixture = dict(example["input"])
            passed, score, failure_reason = score_lesson_fixture(fixture)
            if passed:
                passed_count += 1
            conn.execute(
                """
                INSERT INTO ai_eval_results
                  (run_id, example_id, output, score, passed, failure_reason)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s)
                """,
                (
                    run_id,
                    int(example["id"]),
                    json.dumps({"name": fixture.get("name")}),
                    score,
                    passed,
                    failure_reason,
                ),
            )
        total = len(examples)
        failed = total - passed_count
        status = "passed" if failed == 0 else "failed"
        conn.execute(
            """
            UPDATE ai_eval_runs
            SET status = %s, total = %s, passed = %s, failed = %s, finished_at = NOW()
            WHERE id = %s
            """,
            (status, total, passed_count, failed, run_id),
        )
    return {"run_id": run_id, "total": total, "passed": passed_count, "failed": failed}
