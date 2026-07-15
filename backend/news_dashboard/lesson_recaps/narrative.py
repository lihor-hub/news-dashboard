"""AI-written weekly learning recap narrative."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _fallback_narrative(recap: dict[str, Any]) -> str:
    completed = int(recap.get("lessons_completed") or 0)
    concepts: list[dict[str, Any]] = recap.get("key_concepts") or []
    top_concept = concepts[0].get("concept") if concepts else None

    if completed <= 0:
        return "You didn't finish any lessons this week — your next recap is a fresh start."
    if top_concept:
        return (
            f"You completed {completed} lessons this week, with a recurring focus on {top_concept}."
        )
    return f"You completed {completed} lessons this week."


def generate_lesson_recap_narrative(recap: dict[str, Any]) -> str:
    """Generate a short AI narrative for a weekly learning recap.

    Takes the recap dict from
    ``lesson_recaps.service.assemble_weekly_lesson_recap()`` and asks the chat
    model for a "here's what you learned this week" review grounded strictly
    in the given metrics. Falls back to a deterministic template sentence if
    the LLM is not configured or the call fails, matching the
    graceful-degradation contract of ``recaps.narrative.generate_recap_narrative``.
    """
    fallback = _fallback_narrative(recap)

    try:
        from langchain_core.prompts import ChatPromptTemplate

        from news_dashboard.ai_client import free_llm_config, get_chat_model, response_text

        api_key, base_url = free_llm_config()
        if not api_key:
            return fallback

        model = os.getenv("OPENAI_BRIEFING_MODEL", "gpt-4o-mini")

        metrics = {k: v for k, v in recap.items() if k != "generated_at"}

        prompt = (
            "Write a weekly learning review in the voice of 'here's what you "
            "learned this week', addressed directly to the reader (second "
            "person). Write exactly 2 short paragraphs, roughly 60-120 words "
            "total. Ground everything strictly in the metrics below — do not "
            "invent lessons, concepts, or numbers that are not present in the "
            "data. Mention repeated themes and unfinished lessons when present.\n\n"
            f"Recap metrics (JSON):\n{json.dumps(metrics, default=str)}\n\n"
            "Reply with only the narrative text, as plain paragraphs separated "
            "by a blank line."
        )

        chat_model = get_chat_model(api_key=api_key, base_url=base_url, model=model).bind(
            max_tokens=300, temperature=0.7
        )
        template = ChatPromptTemplate.from_messages([("human", "{prompt}")])
        response = (template | chat_model).invoke(
            {"prompt": prompt},
            config={"metadata": {"max_tokens": 300, "temperature": 0.7}},
        )
        narrative = response_text(response).strip()
        if narrative:
            return narrative
    except Exception:
        logger.warning("Lesson recap narrative LLM generation failed; using default message")

    return fallback
