from unittest.mock import MagicMock, patch

from news_dashboard.ai_client import ManagedPrompt
from news_dashboard.body_fetch import fetch_and_cache_body, translate_body
from news_dashboard.db import connect
from news_dashboard.ingest.service import detect_and_translate_article


def test_detect_and_translate_article_english() -> None:
    # When source_lang is en, no translation API call should be made
    mock_client = MagicMock()
    with patch("openai.OpenAI", return_value=mock_client):
        title, summary, lang, orig = detect_and_translate_article(
            "English Title", "English Summary", "en"
        )
    assert title == "English Title"
    assert summary == "English Summary"
    assert lang == "en"
    assert orig is None
    mock_client.chat.completions.create.assert_not_called()


def test_detect_and_translate_article_japanese() -> None:
    # Mocking OpenAI response for Japanese translation
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = (
        '{"detected_lang": "ja", "translated_title": "Translated Title", '
        '"translated_summary": "Translated Summary", "needs_translation": true}'
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        title, summary, lang, orig = detect_and_translate_article(
            "日本語タイトル", "日本語サマリー", "ja"
        )

    assert title == "Translated Title"
    assert summary == "Translated Summary"
    assert lang == "ja"
    assert orig == "日本語タイトル"
    mock_client.chat.completions.create.assert_called_once()


def test_translate_body_japanese() -> None:
    # Mocking OpenAI response for Japanese body translation
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "Translated Body Text"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        translated = translate_body("日本語の本文", "ja")

    assert translated == "Translated Body Text"
    mock_client.chat.completions.create.assert_called_once()


def test_translate_body_uses_managed_chat_prompt() -> None:
    from news_dashboard.body_fetch import _TRANSLATE_BODY_PROMPT

    managed = ManagedPrompt(
        text=None,
        messages=[{"role": "system", "content": "compiled"}, {"role": "user", "content": "本文"}],
        langfuse_prompt=object(),
    )
    completion = MagicMock()
    completion.choices[0].message.content = "Translated"

    with (
        patch("news_dashboard.ai_client.free_llm_config", return_value=("key", None)),
        patch("news_dashboard.ai_client.get_chat_client", return_value=MagicMock()),
        patch("news_dashboard.ai_client.get_prompt", return_value=managed) as get_prompt,
        patch("news_dashboard.ai_client.chat_create", return_value=completion) as chat_create,
    ):
        assert translate_body("本文", "ja") == "Translated"

    get_prompt.assert_called_once_with(
        "translate-body",
        fallback=_TRANSLATE_BODY_PROMPT,
        prompt_type="chat",
        label="production",
        variables={"from_lang": "ja", "body": "本文"},
    )
    assert chat_create.call_args.kwargs["prompt"] is managed
    assert chat_create.call_args.kwargs["messages"] == managed.messages


def test_detect_and_translate_article_uses_managed_chat_prompt() -> None:
    from news_dashboard.ingest.service import _TRANSLATE_ARTICLE_PROMPT

    managed = ManagedPrompt(
        text=None,
        messages=[{"role": "system", "content": "compiled translation"}],
        langfuse_prompt=object(),
    )
    completion = MagicMock()
    completion.choices[0].message.content = (
        '{"detected_lang":"ja","translated_title":"English title",'
        '"translated_summary":"English summary","needs_translation":true}'
    )

    with (
        patch("news_dashboard.ai_client.free_llm_config", return_value=("key", None)),
        patch("news_dashboard.ai_client.get_chat_client", return_value=MagicMock()),
        patch("news_dashboard.ai_client.get_prompt", return_value=managed) as get_prompt,
        patch("news_dashboard.ai_client.chat_create", return_value=completion) as chat_create,
    ):
        result = detect_and_translate_article("日本語タイトル", "日本語要約", "ja")

    assert result == ("English title", "English summary", "ja", "日本語タイトル")
    get_prompt.assert_called_once_with(
        "translate-article",
        fallback=_TRANSLATE_ARTICLE_PROMPT,
        prompt_type="chat",
        label="production",
        variables={"title": "日本語タイトル", "summary": "日本語要約"},
    )
    assert chat_create.call_args.kwargs["prompt"] is managed
    assert chat_create.call_args.kwargs["messages"] == managed.messages


def test_fetch_and_cache_body_translates_non_english(pg_clean: str) -> None:
    # Insert an article with non-English language metadata
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, lang)
            VALUES ('ja-src', 'Japanese Source', 'https://ja.example.com', 'tech', 'rss_feed', 'ja')
            """
        )
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, summary, detected_lang, original_title
            )
            VALUES (
              'https://ja.example.com/a1', 'https://ja.example.com/a1',
              'Translated Title', 'ja-src', 'Japanese Source', 'tech', 'rss_feed',
              'Translated Summary', 'ja', '日本語タイトル'
            )
            RETURNING id
            """
        ).fetchone()
    article_id = int(row["id"])

    # Mock extract_body to return Japanese body text
    # Mock translate_body (or the OpenAI client it uses) to return English translated body
    mock_completion = MagicMock()
    mock_completion.choices[0].message.content = "Translated English Body"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
        patch("news_dashboard.body_fetch.extract_body", return_value=("日本語の本文", "ok")),
    ):
        article = fetch_and_cache_body(article_id, db_path=pg_clean)

    assert article is not None
    assert article["body"] == "Translated English Body"
    assert article["original_body"] == "日本語の本文"
    assert article["body_status"] == "ok"

    # Verify what is stored in the database
    with connect(database_url=pg_clean) as conn:
        db_row = conn.execute("SELECT * FROM articles WHERE id = %s", (article_id,)).fetchone()
    assert db_row["body"] == "Translated English Body"
    assert db_row["original_body"] == "日本語の本文"
    assert db_row["detected_lang"] == "ja"
    assert db_row["original_title"] == "日本語タイトル"
