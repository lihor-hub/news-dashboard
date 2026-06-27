"""Feedback-driven prompt auto-improvement.

Closes the loop on the user-feedback scores collected via ``/api/feedback``:
pull the recent thumbs-down answers for a managed prompt from Langfuse, ask an
LLM to revise that prompt so it would have handled those cases better, and save
the result back to Langfuse as a **new, non-production prompt version** (label
``candidate``). A human then reviews the candidate in the Langfuse UI and
promotes it to ``production`` if it is an improvement — the loop never
auto-deploys a prompt.

All Langfuse access degrades gracefully: when tracing is disabled or the API is
unreachable, the entry point raises a clear error instead of silently doing
nothing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from news_dashboard.ai_client import _client, chat_create, get_chat_client, langfuse_enabled

logger = logging.getLogger(__name__)

CANDIDATE_LABEL = "candidate"
DEFAULT_OPTIMIZER_MODEL = "gpt-4o"

_OPTIMIZER_INSTRUCTIONS = (
    "You are a prompt engineer improving a system prompt for an LLM feature. "
    "Below is the CURRENT system prompt, followed by real examples where users "
    "marked the assistant's answer as unhelpful (thumbs down). Rewrite the "
    "system prompt so it would handle these failure cases better, while "
    "preserving its original intent, constraints, and output format. Keep it "
    "concise. Do not invent new capabilities or remove safety constraints. "
    "Return ONLY the revised system prompt text, with no preamble or commentary."
)


class PromptOptimizerError(Exception):
    """Raised when prompt optimization cannot proceed."""


@dataclass(frozen=True)
class NegativeExample:
    """A single thumbs-down answer with the question that produced it."""

    question: str
    answer: str
    comment: str | None = None


@dataclass(frozen=True)
class OptimizationResult:
    """Outcome of an optimization run."""

    prompt_name: str
    example_count: int
    new_version: int | None
    candidate_label: str
    proposed_text: str


def _score_is_negative(value: Any) -> bool:
    """True when a ``user-thumbs`` BOOLEAN/NUMERIC score reads as thumbs-down."""
    try:
        return float(value) <= 0
    except (TypeError, ValueError):
        return False


def collect_negative_examples(
    *,
    score_name: str = "user-thumbs",
    days: int = 14,
    limit: int = 50,
) -> list[NegativeExample]:
    """Fetch recent thumbs-down answers and their questions from Langfuse."""
    if not langfuse_enabled():
        msg = "Langfuse is not configured (LANGFUSE_PUBLIC_KEY/SECRET_KEY missing)."
        raise PromptOptimizerError(msg)

    api = _client().api
    from_ts = datetime.now(timezone.utc) - timedelta(days=days)
    scores = api.scores_v3.get_many_v3(name=score_name, from_timestamp=from_ts, limit=limit)

    examples: list[NegativeExample] = []
    for score in scores.data or []:
        if not _score_is_negative(getattr(score, "value", None)):
            continue
        trace_id = getattr(score, "trace_id", None)
        if not trace_id:
            continue
        try:
            trace = api.trace.get(trace_id)
        except Exception as exc:
            logger.warning("could not fetch trace %s: %s", trace_id, exc)
            continue
        question = _extract_question(trace.input)
        answer = str(trace.output or "").strip()
        if question and answer:
            examples.append(
                NegativeExample(
                    question=question,
                    answer=answer,
                    comment=getattr(score, "comment", None),
                )
            )
    return examples


def _extract_question(trace_input: Any) -> str:
    """Pull the user question out of a trace input (dict or raw string)."""
    if isinstance(trace_input, dict):
        return str(trace_input.get("query") or "").strip()
    return str(trace_input or "").strip()


def build_optimizer_prompt(current_text: str, examples: list[NegativeExample]) -> str:
    """Build the meta-prompt sent to the optimizing LLM (pure, testable)."""
    blocks = [f"CURRENT SYSTEM PROMPT:\n{current_text}", "\nUNHELPFUL EXAMPLES:"]
    for i, ex in enumerate(examples, 1):
        block = f"\nExample {i}:\nUser question: {ex.question}\nAssistant answer: {ex.answer}"
        if ex.comment:
            block += f"\nUser comment: {ex.comment}"
        blocks.append(block)
    return "\n".join(blocks)


def _optimizer_ai_config() -> tuple[str, str | None]:
    """Resolve (api_key, base_url) for prompt optimization.

    Targets the free LLM gateway via ``OPENAI_OPTIMIZER_BASE_URL`` /
    ``OPENAI_OPTIMIZER_API_KEY``, falling back to the briefing gateway config
    and then the shared ``OPENAI_BASE_URL`` / ``OPENAI_API_KEY``. The base URL
    is optional; when unset the official OpenAI endpoint is used.
    """
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        msg = (
            "Prompt optimization requires an API key. Set FREE_LLM_API_KEY "
            "(or OPENAI_API_KEY) in the app environment."
        )
        raise PromptOptimizerError(msg)
    return api_key, base_url


def _propose_revision(current_text: str, examples: list[NegativeExample], *, model: str) -> str:
    """Call the LLM to draft an improved prompt. Traced like any other call."""
    api_key, base_url = _optimizer_ai_config()
    client = get_chat_client(api_key=api_key, base_url=base_url)
    response = chat_create(
        client,
        name="prompt-optimizer",
        tags=["prompt-optimizer"],
        model=model,
        messages=[
            {"role": "system", "content": _OPTIMIZER_INSTRUCTIONS},
            {"role": "user", "content": build_optimizer_prompt(current_text, examples)},
        ],
        max_tokens=1024,
    )
    return (response.choices[0].message.content or "").strip()


def optimize_prompt(
    *,
    prompt_name: str,
    fallback: str = "",
    score_name: str = "user-thumbs",
    days: int = 14,
    max_examples: int = 50,
    model: str | None = None,
) -> OptimizationResult:
    """Run one feedback-driven improvement pass for *prompt_name*.

    Fetches the current production prompt, collects recent thumbs-down answers,
    asks the LLM for a revision, and saves it to Langfuse under the
    ``candidate`` label for human review. Raises :class:`PromptOptimizerError`
    when there is nothing to learn from (no negative feedback) or Langfuse is
    unavailable.
    """
    resolved_model = (
        model if model is not None else os.getenv("OPENAI_OPTIMIZER_MODEL", DEFAULT_OPTIMIZER_MODEL)
    )
    examples = collect_negative_examples(score_name=score_name, days=days, limit=max_examples)
    if not examples:
        msg = f"No '{score_name}' thumbs-down feedback in the last {days} days; nothing to do."
        raise PromptOptimizerError(msg)

    client = _client()
    try:
        current = client.get_prompt(prompt_name, label="production", type="text", fallback=fallback)
        current_text = current.prompt
    except Exception as exc:
        msg = f"Could not load current prompt '{prompt_name}': {exc}"
        raise PromptOptimizerError(msg) from exc

    proposed = _propose_revision(current_text, examples, model=resolved_model)
    if not proposed:
        msg = "The optimizer model returned an empty prompt."
        raise PromptOptimizerError(msg)

    created = client.create_prompt(
        name=prompt_name,
        prompt=proposed,
        type="text",
        labels=[CANDIDATE_LABEL],
        commit_message=f"Auto-proposed from {len(examples)} thumbs-down examples ({days}d)",
    )
    return OptimizationResult(
        prompt_name=prompt_name,
        example_count=len(examples),
        new_version=getattr(created, "version", None),
        candidate_label=CANDIDATE_LABEL,
        proposed_text=proposed,
    )
