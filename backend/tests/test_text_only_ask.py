from __future__ import annotations

from unittest.mock import patch

import pytest

from news_dashboard.db import connect, init_db
from news_dashboard.embeddings import ask


@pytest.mark.parametrize("provider", ["chatgpt", "ollama"])
def test_ask_works_without_embedding_credentials(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    monkeypatch.setenv("AI_TEXT_PROVIDER", provider)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    init_db(pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO sources(slug,name,url,category,kind) VALUES ('test','Test','https://example.test/rss','tech','rss_feed')"
        )
        for i in range(1, 7):
            conn.execute(
                "INSERT INTO articles(id,url,canonical_url,title,source_slug,source_name,"
                "category,kind,status,summary) "
                "VALUES (%s,%s,%s,%s,'test','Test','tech','rss_feed',%s,%s)",
                (
                    i,
                    f"https://example.test/{i}",
                    f"https://example.test/{i}",
                    "PostgreSQL release" if i == 1 else "Unrelated news",
                    "saved" if i < 6 else "archived",
                    "PostgreSQL improvements" if i == 1 else "Other news",
                ),
            )
    with (
        patch(
            "news_dashboard.embeddings._embed", side_effect=AssertionError("embedding API called")
        ),
        patch(
            "news_dashboard.embeddings._generate_answer", return_value=("answer", None)
        ) as answer,
    ):
        result = ask("PostgreSQL", pg_clean)
    assert result["answer"] == "answer"
    assert result["sources"][0]["id"] == 1
    assert {source["id"] for source in result["sources"]} == {1, 2, 3, 4, 5}
    assert "PostgreSQL release" in answer.call_args.kwargs["user_prompt"]


@pytest.mark.parametrize(
    ("include_all", "expected"), [(False, {1, 2, 3, 4, 5}), (True, {1, 2, 3, 4, 5, 6})]
)
def test_text_retrieval_keeps_user_corpus_private(
    pg_clean: str, include_all: bool, expected: set[int]
) -> None:
    from news_dashboard.embeddings import _text_retrieval

    init_db(pg_clean)
    with connect(database_url=pg_clean) as conn:
        for user_id in (1, 2):
            conn.execute(
                "INSERT INTO users(id,username,password_hash) VALUES (%s,%s,'test-hash')",
                (user_id, f"user-{user_id}"),
            )
        for slug, owner in [("public", None), ("private", 2), ("disabled", None)]:
            conn.execute(
                "INSERT INTO sources(slug,name,url,category,kind,owner_user_id) "
                "VALUES (%s,%s,%s,'tech','rss_feed',%s)",
                (slug, slug, f"https://example.test/{slug}/rss", owner),
            )
        conn.execute(
            "INSERT INTO user_sources(user_id,source_slug,enabled) VALUES (1,'disabled',FALSE)"
        )
        for i in range(1, 10):
            slug = {7: "private", 8: "disabled"}.get(i, "public")
            conn.execute(
                "INSERT INTO articles(id,url,canonical_url,title,source_slug,source_name,"
                "category,kind,status,summary) VALUES (%s,%s,%s,'PostgreSQL',%s,%s,"
                "'tech','rss_feed','saved','release')",
                (i, f"https://example.test/{i}", f"https://example.test/{i}", slug, slug),
            )
            state = "today" if i == 6 else ("archived" if i == 9 else "done")
            conn.execute(
                "INSERT INTO user_article_state(user_id,article_id,state) VALUES (1,%s,%s)",
                (i, state),
            )
    rows = _text_retrieval("PostgreSQL", pg_clean, include_all=include_all, user_id=1, limit=8)
    assert {row["id"] for row in rows} == expected
    assert rows[0]["eligible_count"] == len(expected)
