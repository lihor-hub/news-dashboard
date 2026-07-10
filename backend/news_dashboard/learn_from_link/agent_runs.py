"""Per-run/per-step trace bookkeeping for the Learn from Link generation pipeline.

Records prompt/model/config version metadata plus per-stage status, latency,
and (where applicable) token/cost bookkeeping in ``learning_agent_runs`` /
``learning_agent_steps``, mirroring the run/step convention already used by
``news_dashboard.briefing_agent`` for the briefing pipeline.

Runtime SQL uses psycopg %s parameter style. No SQLite fallback.
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Jsonb

from news_dashboard.db import connect, init_db, row_to_dict

logger = logging.getLogger(__name__)

STEP_FETCH = "fetch"
STEP_EXTRACTION = "extraction"
STEP_SYNTHESIS = "synthesis"
STEP_CITATION_VERIFICATION = "citation_verification"
STEP_PERSISTENCE = "persistence"

STEP_ORDER = (
    STEP_FETCH,
    STEP_EXTRACTION,
    STEP_SYNTHESIS,
    STEP_CITATION_VERIFICATION,
    STEP_PERSISTENCE,
)

# Bumped whenever the deterministic synthesis template in
# ``news_dashboard.learn_from_link.service.generate_structured_lesson_detail``
# changes in a way that could shift eval baselines. There is no separate LLM
# "prompt" for core synthesis today (it's template/heuristic-based, not a
# model call), so this stands in as the versioned unit of behavior.
SYNTHESIS_PROMPT_VERSION = "lesson-synthesis-v1"

# Coarse USD-per-1K-token estimates, used only for admin/debug cost visibility
# on steps that do call an LLM (e.g. personal relevance). Not billing-accurate;
# when Langfuse is configured, ``/api/admin/ai/metrics`` remains the source of
# truth for actual billed cost.
_MODEL_PRICE_PER_1K_TOKENS: dict[str, float] = {
    "gpt-4o-mini": 0.00015,
}
_DEFAULT_PRICE_PER_1K_TOKENS = 0.0005


def estimate_cost_usd(
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float | None:
    """Return a rough USD cost estimate for a step's token usage, or None if unknown."""
    if prompt_tokens is None and completion_tokens is None:
        return None
    total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
    price = _MODEL_PRICE_PER_1K_TOKENS.get(model or "", _DEFAULT_PRICE_PER_1K_TOKENS)
    return round((total_tokens / 1000) * price, 6)


def start_run(
    database_url: str | None,
    *,
    lesson_id: int,
    user_id: int,
    prompt_version: str,
    model_version: str,
    config: dict[str, Any],
) -> int:
    """Create a new 'running' learning_agent_runs row and return its id."""
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO learning_agent_runs(
              lesson_id, user_id, status, prompt_version, model_version, config
            )
            VALUES (%s, %s, 'running', %s, %s, %s::jsonb)
            RETURNING id
            """,
            (lesson_id, user_id, prompt_version, model_version, Jsonb(config)),
        ).fetchone()
        if row is None:
            msg = "INSERT INTO learning_agent_runs returned no row"
            raise RuntimeError(msg)
        return int(row_to_dict(row)["id"])


def record_step(  # noqa: PLR0913
    database_url: str | None,
    run_id: int,
    step: str,
    ordinal: int,
    *,
    status: str,
    model: str | None = None,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    error: str | None = None,
) -> None:
    """Record one pipeline step's outcome. Failures here are logged, not raised."""
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)
    try:
        with connect(database_url=database_url) as conn:
            conn.execute(
                """
                INSERT INTO learning_agent_steps(
                    run_id, step, ordinal, status, model, latency_ms,
                    prompt_tokens, completion_tokens, cost_usd, error
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, ordinal) DO UPDATE SET
                    status = excluded.status,
                    model = excluded.model,
                    latency_ms = excluded.latency_ms,
                    prompt_tokens = excluded.prompt_tokens,
                    completion_tokens = excluded.completion_tokens,
                    cost_usd = excluded.cost_usd,
                    error = excluded.error
                """,
                (
                    run_id,
                    step,
                    ordinal,
                    status,
                    model,
                    latency_ms,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    error,
                ),
            )
    except Exception:
        logger.exception("Failed to record learning agent step %s for run %d", step, run_id)


def finish_run(
    database_url: str | None,
    run_id: int,
    *,
    status: str,
    retry_count: int = 0,
    failed_step: str | None = None,
    error: str | None = None,
) -> None:
    """Aggregate step latency/tokens/cost and mark a run complete or failed.

    Failures here are logged, not raised, so a bookkeeping problem never takes
    down lesson generation itself.
    """
    try:
        with connect(database_url=database_url) as conn:
            totals_row = conn.execute(
                """
                SELECT
                  SUM(latency_ms) AS total_latency_ms,
                  SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0))
                    AS total_tokens,
                  SUM(cost_usd) AS cost_usd
                FROM learning_agent_steps
                WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()
            totals = row_to_dict(totals_row) if totals_row else {}
            conn.execute(
                """
                UPDATE learning_agent_runs
                SET status = %s, retry_count = %s, failed_step = %s, error = %s,
                    total_latency_ms = %s, total_tokens = %s, cost_usd = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    status,
                    retry_count,
                    failed_step,
                    error,
                    totals.get("total_latency_ms"),
                    totals.get("total_tokens"),
                    totals.get("cost_usd"),
                    run_id,
                ),
            )
    except Exception:
        logger.exception("Failed to finalize learning agent run %d", run_id)


def admin_run_summary(
    *,
    limit: int = 50,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Return recent learning agent runs with their per-step breakdown, for admin/debug."""
    init_db(database_url=database_url)
    limit = max(1, min(limit, 200))
    with connect(database_url=database_url) as conn:
        runs = conn.execute(
            """
            SELECT id, lesson_id, user_id, status, prompt_version, model_version, config,
                   retry_count, total_latency_ms, total_tokens, cost_usd, failed_step, error,
                   created_at, updated_at
            FROM learning_agent_runs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        run_dicts = [row_to_dict(row) for row in runs]
        run_ids = [int(d["id"]) for d in run_dicts]
        steps_by_run: dict[int, list[dict[str, Any]]] = {rid: [] for rid in run_ids}
        if run_ids:
            steps = conn.execute(
                """
                SELECT run_id, step, ordinal, status, model, latency_ms,
                       prompt_tokens, completion_tokens, cost_usd, error, created_at
                FROM learning_agent_steps
                WHERE run_id = ANY(%s)
                ORDER BY run_id, ordinal
                """,
                (run_ids,),
            ).fetchall()
            for step_row in steps:
                step_dict = row_to_dict(step_row)
                if step_dict.get("created_at") is not None:
                    step_dict["created_at"] = step_dict["created_at"].isoformat()
                steps_by_run.setdefault(int(step_dict["run_id"]), []).append(step_dict)

    items = []
    for run_dict in run_dicts:
        run_id = int(run_dict["id"])
        for key in ("created_at", "updated_at"):
            if run_dict.get(key) is not None:
                run_dict[key] = run_dict[key].isoformat()
        run_dict["steps"] = steps_by_run.get(run_id, [])
        items.append(run_dict)
    return {"items": items}
