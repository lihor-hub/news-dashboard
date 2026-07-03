from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db

MAX_TEXT_CHARS = 2000
MAX_COMMENT_CHARS = 500
DEFAULT_PROMPT_VERSION = "local"
DEFAULT_MODEL_VERSION = "local"


def _bounded(value: Any, limit: int = MAX_TEXT_CHARS) -> Any:
    if isinstance(value, str):
        text = re.sub(r"\s+", " ", value).strip()
        return text[:limit]
    if isinstance(value, Mapping):
        return {str(k): _bounded(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [_bounded(v, limit) for v in value[:20]]
    return value


def record_feedback_example(
    *,
    user_id: int,
    trace_id: str,
    helpful: bool,
    comment: str | None = None,
    feature: str = "ask-ai",
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> int:
    init_db(db_path, database_url=database_url)
    expected = {
        "feedback_helpful": helpful,
        "comment": _bounded(comment or "", MAX_COMMENT_CHARS),
    }
    with connect(db_path, database_url=database_url) as conn:
        creator_row = conn.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
        creator_id = user_id if creator_row is not None else None
        row = conn.execute(
            """
            INSERT INTO ai_eval_examples
              (feature, prompt_version, model_version, input, expected_properties,
               source_trace_id, feedback_helpful, created_by_user_id)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
            RETURNING id
            """,
            (
                feature,
                DEFAULT_PROMPT_VERSION,
                DEFAULT_MODEL_VERSION,
                json.dumps({"trace_id": _bounded(trace_id, 200)}),
                json.dumps(expected),
                _bounded(trace_id, 200),
                helpful,
                creator_id,
            ),
        ).fetchone()
    return int(row["id"])


def score_output(
    output: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> tuple[bool, float, str | None]:
    failures: list[str] = []
    citations = _int_set(output.get("citations") or output.get("citation_ids") or [])
    allowed = _int_set(expected.get("allowed_citation_ids") or expected.get("citation_ids") or [])
    if allowed and not citations.issubset(allowed):
        failures.append("unknown citations")
    if expected.get("requires_citation") and not citations:
        failures.append("missing citations")
    if expected.get("weak_retrieval"):
        answer = str(output.get("answer") or output.get("text") or "").lower()
        if "insufficient" not in answer and "not enough context" not in answer:
            failures.append("missing insufficient-context response")
    if expected.get("briefing"):
        sections = output.get("sections")
        if not isinstance(sections, list):
            failures.append("invalid briefing JSON shape")
        elif allowed:
            for section in sections:
                if isinstance(section, Mapping):
                    section_citations = _int_set(section.get("citations") or [])
                    if not section_citations.issubset(allowed):
                        failures.append("unknown briefing citations")
                        break
    min_chars = _optional_int(expected.get("min_chars"))
    max_chars = _optional_int(expected.get("max_chars"))
    text = json.dumps(output, sort_keys=True)
    if min_chars is not None and len(text) < min_chars:
        failures.append("response too short")
    if max_chars is not None and len(text) > max_chars:
        failures.append("response too long")
    passed = not failures
    return passed, 1.0 if passed else 0.0, "; ".join(failures) or None


def run_local_evals(
    *,
    feature: str | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    model_version: str = DEFAULT_MODEL_VERSION,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        run = conn.execute(
            """
            INSERT INTO ai_eval_runs(feature, prompt_version, model_version)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (feature, prompt_version, model_version),
        ).fetchone()
        run_id = int(run["id"])
        params: tuple[Any, ...]
        where = ""
        if feature:
            where = "WHERE feature = %s"
            params = (feature,)
        else:
            params = ()
        examples = conn.execute(
            f"""
            SELECT id, input, expected_properties
            FROM ai_eval_examples
            {where}
            ORDER BY id
            """,
            params,
        ).fetchall()
        passed_count = 0
        for example in examples:
            expected = dict(example["expected_properties"] or {})
            output = _expected_output(example["input"], expected)
            passed, score, failure_reason = score_output(output, expected)
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
                    json.dumps(_bounded(output)),
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


def admin_quality_summary(
    *,
    days: int = 30,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(db_path, database_url=database_url)
    days = max(1, min(days, 365))
    start = datetime.now(timezone.utc) - timedelta(days=days)
    with connect(db_path, database_url=database_url) as conn:
        feedback = conn.execute(
            """
            SELECT feature,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE feedback_helpful IS TRUE) AS positive,
                   COUNT(*) FILTER (WHERE feedback_helpful IS FALSE) AS negative
            FROM ai_eval_examples
            WHERE created_at >= %s
            GROUP BY feature
            ORDER BY total DESC, feature
            """,
            (start,),
        ).fetchall()
        evals = conn.execute(
            """
            SELECT COALESCE(feature, 'all') AS feature,
                   COUNT(*) AS runs,
                   COALESCE(SUM(total), 0) AS total,
                   COALESCE(SUM(passed), 0) AS passed,
                   COALESCE(SUM(failed), 0) AS failed
            FROM ai_eval_runs
            WHERE started_at >= %s AND status != 'running'
            GROUP BY 1
            ORDER BY 1
            """,
            (start,),
        ).fetchall()
        failures = conn.execute(
            """
            SELECT r.feature, e.id AS example_id, er.failure_reason, er.created_at
            FROM ai_eval_results er
            JOIN ai_eval_runs r ON r.id = er.run_id
            JOIN ai_eval_examples e ON e.id = er.example_id
            WHERE er.created_at >= %s AND er.passed IS FALSE
            ORDER BY er.created_at DESC
            LIMIT 10
            """,
            (start,),
        ).fetchall()
    return {
        "range_days": days,
        "feedback": [dict(row) for row in feedback],
        "evals": [
            {
                **dict(row),
                "pass_rate": round(float(row["passed"]) / float(row["total"]), 3)
                if int(row["total"])
                else 0.0,
            }
            for row in evals
        ],
        "recent_failures": [dict(row) for row in failures],
    }


def _expected_output(input_data: Any, expected: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(expected.get("fake_output"), Mapping):
        return dict(expected["fake_output"])
    if isinstance(input_data, Mapping) and isinstance(input_data.get("fake_output"), Mapping):
        return dict(input_data["fake_output"])
    return {"answer": "insufficient context", "citations": expected.get("citation_ids", [])}


def _int_set(value: Any) -> set[int]:
    if not isinstance(value, list):
        return set()
    result: set[int] = set()
    for item in value:
        maybe = _optional_int(item)
        if maybe is not None:
            result.add(maybe)
    return result


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
