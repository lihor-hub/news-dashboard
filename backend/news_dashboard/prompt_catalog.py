"""Canonical local fallbacks for prompts managed in Langfuse."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PromptType = Literal["text", "chat"]


@dataclass(frozen=True, slots=True)
class PromptMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class PromptCatalogEntry:
    name: str
    type: PromptType
    prompt: str | tuple[PromptMessage, ...]
    commit_message: str | None = None

    def fallback(self) -> str | list[dict[str, str]]:
        if isinstance(self.prompt, str):
            return self.prompt
        return [{"role": message.role, "content": message.content} for message in self.prompt]


def _text(name: str, prompt: str, commit_message: str | None = None) -> PromptCatalogEntry:
    return PromptCatalogEntry(name, "text", prompt, commit_message)


def _chat(
    name: str,
    *messages: tuple[Literal["system", "user", "assistant"], str],
    commit_message: str | None = None,
) -> PromptCatalogEntry:
    return PromptCatalogEntry(
        name,
        "chat",
        tuple(PromptMessage(role, content) for role, content in messages),
        commit_message,
    )


PROMPT_CATALOG: tuple[PromptCatalogEntry, ...] = (
    _text(
        "ai-body-fetch",
        "Extract the main article text from this HTML. Return only the article body as plain "
        "text, no HTML tags.\n\n{{html}}",
    ),
    _chat(
        "translate-body",
        (
            "system",
            (
                "You are a translation assistant. Translate the following body text from language "
                "code '{{from_lang}}' to English. Return only the translated plain text, "
                "preserving paragraph breaks, and no additional commentary."
            ),
        ),
        ("user", "{{body}}"),
    ),
    _chat(
        "summarize-media-article",
        (
            "system",
            (
                "Summarize this podcast or video transcript as a concise readable article summary "
                "for a news reader."
            ),
        ),
        ("user", "Title: {{title}}\nDescription: {{description}}\nTranscript:\n{{transcript}}"),
    ),
    _chat(
        "translate-article",
        (
            "system",
            (
                "You are a translation assistant. Detect the language of the following text. If it "
                "is not English, translate both the title and the summary/description to English. "
                "Return a JSON object with the following keys:\n"
                '- "detected_lang": the 2-letter ISO 639-1 language code (e.g. "ja", "zh", "ru", '
                '"fr", "de", "en")\n- "translated_title": the translated title in English\n'
                '- "translated_summary": the translated summary/description in English\n'
                '- "needs_translation": boolean indicating if it was translated\n'
            ),
        ),
        ("user", "Title: {{title}}\nSummary: {{summary}}"),
    ),
    _text(
        "topic-cluster-label",
        "You are analyzing a group of related news articles that cover the same story or topic "
        "arc. Based ONLY on the article titles and summaries provided below, generate:\n1. A "
        "concise Story Headline (max 8 words) capturing the central theme.\n2. A one-sentence "
        "Trend Summary explaining the story arc or why these articles are connected.\n\nRespond "
        "in this exact format:\nHEADLINE: <headline here>\nSUMMARY: <one-sentence summary "
        "here>\n\nArticles:\n{{articles_text}}",
    ),
    _text(
        "briefing-push-hook",
        "Write a single punchy mobile push notification hook (max 15 words) that entices the "
        "user to open their news briefing. Top headlines:\n{{headline_block}}\n\nReply with only "
        "the hook text, no quotes or punctuation at the end.",
    ),
    _text(
        "recap-push-hook",
        "Write a single encouraging mobile push notification hook (max 20 words) summarizing "
        "this user's weekly reading recap. Articles read: {{articles_read}}. Top category: "
        "{{top_category}}. Current streak: {{current_streak_days}} day(s).\n\nReply with only the "
        "hook text, no quotes or punctuation at the end.",
    ),
    _text(
        "recommendation-explanation",
        "You are a personalized news assistant. Explain in one short sentence (under 20 words) "
        "why this article matches the user's reading interests.\n\nArticle: "
        '"{{article_title}}"\nSource: {{article_source}}\nCategory: {{article_category}}\nTags: '
        "{{article_tags}}\n\nUser's recent reading history:\n{{history_text}}\n\nReply with just "
        "the explanation sentence, no preamble.",
    ),
    _text(
        "weekly-lesson-recap-narrative",
        "Write a weekly learning review in the voice of 'here's what you learned this week', "
        "addressed directly to the reader (second person). Write exactly 2 short paragraphs, "
        "roughly 60-120 words total. Ground everything strictly in the metrics below — do not "
        "invent lessons, concepts, or numbers that are not present in the data. Mention repeated "
        "themes and unfinished lessons when present.\n\nRecap metrics (JSON):\n{{recap_json}}\n\n"
        "Reply with only the narrative text, as plain paragraphs separated by a blank line.",
    ),
    _text(
        "weekly-quiz",
        "You are a study-aid assistant. Based ONLY on the articles listed below, generate exactly "
        "3 multiple-choice questions that test the reader's understanding of key facts or "
        "arguments. For each question provide:\n- question: the question text\n- options: a JSON "
        "array of exactly 4 answer strings\n- correct_index: 0-based index of the correct answer\n"
        "- explanation: one sentence explaining why that answer is correct, citing the article\n"
        "- article_id: the integer id of the article the question is drawn from\n\nReturn ONLY a "
        "JSON array of 3 objects with those exact keys. No other text.\n\nArticles:\n"
        "{{article_blurbs}}",
    ),
    _text(
        "share-context",
        'Article: "{{article_title}}"\nSummary: {{article_summary}}\n\nSender\'s note: '
        "{{sender_note}}\nHighlighted sections:\n{{annotation_text}}\n\nRecipient's main reading "
        "interests: {{recipient_interests}}\n\nWrite exactly 2 sentences explaining why the sender "
        "highlighted these specific sections and why they are directly relevant to the "
        "recipient's interests. Be specific and personal, not generic.",
    ),
    _text(
        "reading-list-summary",
        "You are helping a reader triage their reading list. Based ONLY on the title and "
        "description below, write one concise sentence (max 40 words) describing what this item "
        "is about, so the reader can decide whether to open it without reading further. Do not "
        "invent details that are not present in the text. Return only the sentence.\n\n"
        "{{reading_list_text}}",
    ),
    _text(
        "weekly-recap-narrative",
        "Write a weekly reading review in the voice of 'here's your week in reading', addressed "
        "directly to the reader (second person). Write exactly 2 short paragraphs, roughly 60-120 "
        "words total. Ground everything strictly in the metrics below — do not invent facts, "
        "activity, or numbers that are not present in the data. If 'saved' or 'dwell' data is "
        "present, mention their reading backlog and skim-vs-read balance.\n\n"
        "Recap metrics (JSON):\n"
        "{{recap_json}}\n\nReply with only the narrative text, as plain paragraphs separated by a "
        "blank line.",
    ),
    _chat(
        "podcast-script-generation",
        (
            "system",
            (
                "You are a podcast script writer. Given a news briefing containing a title, "
                "summary, and several sections, rewrite the content into a natural, conversational "
                "dialogue script between two co-hosts, Alex and Taylor. Alex is a friendly and "
                "curious host, and Taylor is an insightful co-host. They alternate talking, "
                "explaining the news in "
                "an engaging and lively way.\nProduce a JSON object with a single key 'script' "
                "containing a list of dialogue turns. Each turn MUST be an object with these exact "
                "keys:\n  speaker — either 'Alex' or 'Taylor'\n  voice   — 'onyx' for Alex, "
                "'nova' for Taylor\n  text    — the spoken text for this turn\n"
                "Ensure they talk about all the "
                "main "
                "topics in the sections. Return valid JSON only, no markdown wrapper."
            ),
        ),
        ("user", "Please generate a podcast script for the following news:\n\n{{content}}"),
    ),
    _chat(
        "lesson-slide-deck",
        (
            "system",
            (
                "You are the Lesson Slide Deck Generator. Produce a short teaching slide deck "
                "summarizing the lesson below as a shareable learning artifact. Return JSON with a "
                '"slides" array of 6 to 10 slides, each with a "title" and 1-6 "bullets". Ground '
                "every slide in the supplied lesson detail; do not invent facts.\n"
            ),
        ),
        ("user", "{{lesson_content}}"),
    ),
    _chat(
        "lesson-infographic",
        (
            "system",
            (
                "You are the Lesson Infographic Generator. Produce a deterministic, text-first "
                "infographic artifact from the lesson below. Return JSON with title, subtitle, "
                "sections, and footer fields. Each section needs a heading and body. Ground the "
                "artifact only in the supplied lesson detail; do not invent facts, image URLs, or "
                "external assets.\n"
            ),
        ),
        ("user", "{{lesson_content}}"),
    ),
    _chat(
        "lesson-relevance",
        (
            "system",
            (
                "Explain why a lesson is relevant using only the user's provided reading profile. "
                "Return JSON with non-empty explanation and a signals array."
            ),
        ),
        ("user", "{{lesson_context}}\n{{profile_context}}"),
    ),
    _chat(
        "lesson-chat",
        (
            "system",
            (
                "You are the Lesson Follow-up Assistant. Answer follow-up questions about the "
                "lesson below, grounded in the lesson detail and source article content supplied. "
                "If information is not present in the provided context, say so clearly rather than "
                "guessing.\n\n--- LESSON ---\n{{lesson_context}}\n\n--- SOURCE ARTICLE ---\n"
                "{{source_context}}\n"
            ),
        ),
        ("user", "{{question}}"),
    ),
    _chat(
        "briefing-chat",
        (
            "system",
            (
                "You are the Briefing Q&A Assistant. Your job is to answer follow-up questions "
                "about the daily briefing provided below. Ground every answer in the briefing "
                "summary and "
                "the full article texts supplied. If information is not present in the provided "
                "context, say so clearly rather than guessing.\n\n--- BRIEFING ---\n"
                "{{briefing_context}}\n\n"
                "--- CITED ARTICLES ---\n{{articles_context}}\n"
            ),
        ),
        ("user", "{{question}}"),
    ),
)

_PROMPTS_BY_NAME = {entry.name: entry for entry in PROMPT_CATALOG}


def get_catalog_prompt(name: str) -> PromptCatalogEntry:
    """Return a catalog entry by its stable Langfuse name."""
    return _PROMPTS_BY_NAME[name]


def get_text_prompt(name: str) -> str:
    entry = get_catalog_prompt(name)
    if not isinstance(entry.prompt, str):
        raise TypeError(name)
    return entry.prompt


def get_chat_prompt(name: str) -> list[dict[str, str]]:
    entry = get_catalog_prompt(name)
    if isinstance(entry.prompt, str):
        raise TypeError(name)
    return [{"role": message.role, "content": message.content} for message in entry.prompt]
