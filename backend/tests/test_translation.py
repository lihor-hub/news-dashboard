from unittest.mock import MagicMock, patch

from news_dashboard.body_fetch import fetch_and_cache_body, translate_body
from news_dashboard.db import connect
from news_dashboard.ingest import detect_and_translate_article


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
