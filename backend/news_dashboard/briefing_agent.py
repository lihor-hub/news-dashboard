"""Multi-stage briefing generation pipeline support.

Splits briefing generation into named stages — candidate selection, theme
clustering, section drafting, citation verification, and assembly — and
records per-stage status/latency in ``briefing_agent_runs``/
``briefing_agent_steps`` for diagnostics. The AI-calling drafting stage
itself still lives in ``news_dashboard.briefings`` (it needs the OpenAI
client and Langfuse prompt wiring); this module holds the parts that are
pure functions or DB bookkeeping so they can be unit tested without any
network access.

Runtime SQL uses psycopg %s parameter style. No SQLite fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from news_dashboard.db import connect, row_to_dict

logger = logging.getLogger(__name__)

STAGE_CANDIDATE_SELECTION = "candidate_selection"
STAGE_THEME_CLUSTERING = "theme_clustering"
STAGE_DRAFTING = "drafting"
STAGE_CITATION_VERIFICATION = "citation_verification"
STAGE_ASSEMBLY = "assembly"

STAGE_ORDER = (
    STAGE_CANDIDATE_SELECTION,
    STAGE_THEME_CLUSTERING,
    STAGE_DRAFTING,
    STAGE_CITATION_VERIFICATION,
    STAGE_ASSEMBLY,
)


@dataclass
class Theme:
    """A group of candidate articles sharing a category label."""

    label: str
    candidates: list[dict[str, Any]]


def cluster_themes(candidates: list[dict[str, Any]]) -> list[Theme]:
    """Group candidates into themes by category, preserving relative rank order.

    This is a deterministic, no-AI-call stage: it exists so the drafting
    stage can be handed theme-grouped context instead of a flat candidate
    list, and so clustering can be tested and iterated on independently of
    the AI call.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for candidate in candidates:
        label = str(candidate.get("category") or "General").strip() or "General"
        if label not in groups:
            groups[label] = []
            order.append(label)
        groups[label].append(candidate)
    return [Theme(label=label, candidates=groups[label]) for label in order]


def flatten_themes(themes: list[Theme]) -> list[dict[str, Any]]:
    """Flatten clustered themes back into a single ordered candidate list."""
    flattened: list[dict[str, Any]] = []
    for theme in themes:
        flattened.extend(theme.candidates)
    return flattened


def verify_citations(
    raw: dict[str, Any], candidate_ids: set[int]
) -> tuple[dict[str, Any], list[str]]:
    """Validate structure and strip citations that reference unknown article IDs.

    Every section's claim must be backed by at least one cited article drawn
    from the candidate set; citations outside that set are dropped. Returns
    the cleaned content plus the titles of any sections where every proposed
    citation was unsupported and had to be dropped entirely, so the caller
    can flag or log the loss of grounding.

    Raises:
        ValueError: the AI response is missing required keys.
        TypeError: ``sections`` is present but not a list.
    """
    required = {"title", "summary", "sections"}
    missing = required - raw.keys()
    if missing:
        msg = f"AI response missing required keys: {missing}"
        raise ValueError(msg)

    sections = raw.get("sections") or []
    if not isinstance(sections, list):
        msg = "AI response 'sections' must be a list"
        raise TypeError(msg)

    clean_sections = []
    unsupported_sections: list[str] = []
    for section in sections:
        proposed = section.get("citations") or []
        citations = [c for c in proposed if int(c) in candidate_ids]
        if proposed and not citations:
            unsupported_sections.append(str(section.get("title", "")))
        clean_sections.append(
            {
                "title": section.get("title", ""),
                "body": section.get("body", ""),
                "citations": citations,
            }
        )

    worth_opening = [int(c) for c in (raw.get("worth_opening") or []) if int(c) in candidate_ids]

    content = {
        "title": str(raw.get("title", "")),
        "summary": str(raw.get("summary", "")),
        "sections": clean_sections,
        "worth_opening": worth_opening,
    }
    return content, unsupported_sections


# ── Per-stage run/step bookkeeping ────────────────────────────────────────────


def start_run(database_url: str | None, user_id: int | None) -> int:
    """Create a new 'running' briefing_agent_runs row and return its id."""
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO briefing_agent_runs(user_id, status)
            VALUES (%s, 'running')
            RETURNING id
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            msg = "INSERT INTO briefing_agent_runs returned no row"
            raise RuntimeError(msg)
        return int(row_to_dict(row)["id"])


def record_step(  # noqa: PLR0913
    database_url: str | None,
    run_id: int,
    stage: str,
    ordinal: int,
    *,
    status: str,
    model: str | None = None,
    latency_ms: int | None = None,
    error: str | None = None,
) -> None:
    """Record one pipeline stage's outcome. Failures here are logged, not raised."""
    try:
        with connect(database_url=database_url) as conn:
            conn.execute(
                """
                INSERT INTO briefing_agent_steps(
                    run_id, stage, ordinal, status, model, latency_ms, error
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, ordinal) DO UPDATE SET
                    status = excluded.status,
                    model = excluded.model,
                    latency_ms = excluded.latency_ms,
                    error = excluded.error
                """,
                (run_id, stage, ordinal, status, model, latency_ms, error),
            )
    except Exception:
        logger.exception("Failed to record briefing agent step %s for run %d", stage, run_id)


def finish_run(
    database_url: str | None,
    run_id: int,
    *,
    status: str,
    briefing_id: int | None = None,
    failed_stage: str | None = None,
    error: str | None = None,
) -> None:
    """Mark a briefing_agent_runs row complete or failed. Failures here are logged, not raised."""
    try:
        with connect(database_url=database_url) as conn:
            conn.execute(
                """
                UPDATE briefing_agent_runs
                SET status = %s, briefing_id = %s, failed_stage = %s, error = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (status, briefing_id, failed_stage, error, run_id),
            )
    except Exception:
        logger.exception("Failed to finalize briefing agent run %d", run_id)
