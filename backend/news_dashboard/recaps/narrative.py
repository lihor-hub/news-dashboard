"""AI-written weekly recap narrative (long form, for the recap page)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _fallback_narrative(recap: dict[str, Any]) -> str:
    articles_read = int(recap.get("articles_read") or 0)
    minutes_read = recap.get("minutes_read") or 0
    categories: list[dict[str, Any]] = recap.get("categories") or []
    top_category = categories[0].get("category") if categories else None

    if articles_read <= 0:
        return "You didn't read any articles this week — your next recap is a fresh start."
    if top_category:
        return (
            f"You read {articles_read} articles in {minutes_read} minutes this week, "
            f"mostly {top_category}."
        )
    return f"You read {articles_read} articles in {minutes_read} minutes this week."


def generate_recap_narrative(recap: dict[str, Any]) -> str:
    """Generate a 2-paragraph AI narrative for a weekly recap.

    Takes the recap dict from ``recaps.service.assemble_weekly_recap()`` and
    asks the chat model for a longer, second-person "week in reading" review
    grounded strictly in the given metrics. Falls back to a deterministic
    template sentence if the LLM is not configured or the call fails, matching
    the graceful-degradation contract of ``push.generate_recap_push_hook``.
    """
    fallback = _fallback_narrative(recap)

    try:
        from news_dashboard.ai_client import (
            chat_create,
            free_llm_config,
            get_chat_client,
            get_prompt,
        )

        api_key, base_url = free_llm_config()
        if not api_key:
            return fallback

        client = get_chat_client(api_key=api_key, base_url=base_url)
        model = os.getenv("OPENAI_BRIEFING_MODEL", "gpt-4o-mini")

        metrics = {k: v for k, v in recap.items() if k != "generated_at"}

        recap_json = json.dumps(metrics, default=str)
        prompt = get_prompt(
            "weekly-recap-narrative",
            label="production",
            prompt_type="text",
            fallback=(
                "Write a weekly reading review in the voice of 'here's your week in "
                "reading', addressed directly to the reader (second person). "
                "Write exactly 2 short paragraphs, roughly 60-120 words total. "
                "Ground everything strictly in the metrics below — do not invent "
                "facts, activity, or numbers that are not present in the data. "
                "If 'saved' or 'dwell' data is present, mention their reading "
                "backlog and skim-vs-read balance.\n\n"
                "Recap metrics (JSON):\n{{recap_json}}\n\n"
                "Reply with only the narrative text, as plain paragraphs separated "
                "by a blank line."
            ),
            variables={"recap_json": recap_json},
        )

        response = chat_create(
            client,
            name="weekly-recap-narrative",
            tags=["recap"],
            prompt=prompt,
            model=model,
            messages=[{"role": "user", "content": prompt.text}],
            max_tokens=300,
            temperature=0.7,
        )
        narrative = (response.choices[0].message.content or "").strip()
        if narrative:
            return narrative
    except Exception:
        logger.warning("Recap narrative LLM generation failed; using default message")

    return fallback
