"""Tests for LLM-backed entity extraction and the knowledge graph."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from news_dashboard.db import connect
from news_dashboard.entities import (
    EntitiesNotConfiguredError,
    _parse_entities,
    _parse_relationships,
    extract_entities,
    extract_entity_relationships,
    extract_missing_entities,
    extract_missing_entity_relationships,
    get_or_extract_entities,
    knowledge_graph,
    sync_cached_entities_to_graph,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _seed_source(pg_url: str, slug: str, *, owner_user_id: int | None = None) -> None:
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, owner_user_id)
            VALUES (%s, %s, %s, 'tech', 'rss_feed', %s)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug, f"https://{slug}.example", owner_user_id),
        )


def _seed_article(
    pg_url: str,
    *,
    slug: str = "ent-src",
    url_slug: str,
    title: str,
    summary: str = "Summary.",
    entities: str | None = None,
) -> int:
    _seed_source(pg_url, slug)
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, summary, entities, discovered_at
            )
            VALUES (%s, %s, %s, %s, %s, 'tech', 'rss_feed', %s, %s, NOW())
            RETURNING id
            """,
            (
                f"https://{slug}.example/{url_slug}",
                f"https://{slug}.example/{url_slug}",
                title,
                slug,
                slug,
                summary,
                entities,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _seed_user(pg_url: str, username: str) -> int:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'x') RETURNING id",
            (username,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _entities_json(*pairs: tuple[str, str]) -> str:
    return json.dumps({"v": 1, "entities": [{"name": n, "type": t} for n, t in pairs]})


class _MockModel(RunnableLambda[Any, AIMessage]):
    def __init__(self, content: str) -> None:
        self.calls: list[Any] = []
        self.content = content
        super().__init__(self._answer)

    def _answer(self, value: Any) -> AIMessage:
        self.calls.append(value)
        return AIMessage(content=self.content)


def _mock_llm(content: str) -> _MockModel:
    return _MockModel(content)


# ── _parse_entities ───────────────────────────────────────────────────────────


def test_parse_entities_handles_fenced_json() -> None:
    payload = '[{"name": "OpenAI", "type": "org"}, {"name": "Sam Altman", "type": "person"}]'
    raw = f"```json\n{payload}\n```"
    parsed = _parse_entities(raw)
    assert parsed == [
        {"name": "OpenAI", "type": "org"},
        {"name": "Sam Altman", "type": "person"},
    ]


def test_parse_entities_drops_invalid_types_and_dedupes() -> None:
    raw = json.dumps(
        [
            {"name": "OpenAI", "type": "org"},
            {"name": "openai", "type": "org"},  # duplicate, case-insensitive
            {"name": "Something", "type": "alien"},  # invalid type
            {"name": "", "type": "org"},  # empty name
            {"name": "Paris", "type": "place"},
        ]
    )
    parsed = _parse_entities(raw)
    assert parsed == [{"name": "OpenAI", "type": "org"}, {"name": "Paris", "type": "place"}]


def test_parse_entities_returns_empty_for_garbage() -> None:
    assert _parse_entities("not json at all") == []
    assert _parse_entities(json.dumps({"name": "x"})) == []


def test_parse_relationships_validates_entities_and_dedupes() -> None:
    raw = json.dumps(
        [
            {
                "source_name": "OpenAI",
                "source_type": "org",
                "target_name": "Sam Altman",
                "target_type": "person",
                "relationship_type": "led_by",
                "label": "led by",
                "confidence": 0.9,
            },
            {
                "source_name": "openai",
                "source_type": "org",
                "target_name": "Sam Altman",
                "target_type": "person",
                "relationship_type": "led_by",
                "label": "duplicate",
                "confidence": 0.7,
            },
            {
                "source_name": "OpenAI",
                "source_type": "org",
                "target_name": "Unknown",
                "target_type": "org",
                "relationship_type": "mentions",
            },
        ]
    )
    entities = [{"name": "OpenAI", "type": "org"}, {"name": "Sam Altman", "type": "person"}]

    assert _parse_relationships(raw, entities) == [
        {
            "source_name": "OpenAI",
            "source_type": "org",
            "target_name": "Sam Altman",
            "target_type": "person",
            "relationship_type": "led_by",
            "label": "led by",
            "confidence": 0.9,
        }
    ]


def test_parse_relationships_clamps_malformed_confidence() -> None:
    raw = json.dumps(
        [
            {
                "source_name": "OpenAI",
                "source_type": "org",
                "target_name": "Sam Altman",
                "target_type": "person",
                "relationship_type": "led_by",
                "label": "led by",
                "confidence": "not-a-number",
            }
        ]
    )
    entities = [{"name": "OpenAI", "type": "org"}, {"name": "Sam Altman", "type": "person"}]

    assert _parse_relationships(raw, entities)[0]["confidence"] == 0.0


# ── extract_entities ──────────────────────────────────────────────────────────


def test_extract_entities_raises_without_api_key() -> None:
    import os

    env = dict(os.environ.items())
    for key in ("FREE_LLM_API_KEY", "FREE_LLM_BASE_URL", "OPENAI_API_KEY"):
        env.pop(key, None)
    with patch.dict("os.environ", env, clear=True), pytest.raises(EntitiesNotConfiguredError):
        extract_entities({"id": 1, "title": "T", "summary": "S", "body": None})


def test_extract_entities_calls_llm_and_returns_parsed_list() -> None:
    model = _mock_llm('[{"name": "OpenAI", "type": "org"}, {"name": "OpenAI", "type": "org"}]')
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_chat_model", return_value=model) as factory,
    ):
        result = extract_entities(
            {"id": 1, "title": "OpenAI ships", "summary": "OpenAI news", "body": "text"}
        )
    assert result == [{"name": "OpenAI", "type": "org"}]
    assert len(model.calls) == 1
    factory.assert_called_once_with(
        api_key="sk-test", base_url=None, model="gpt-4o-mini", max_tokens=512
    )


def test_extract_entities_attaches_langfuse_callback_and_managed_prompt() -> None:
    from langchain_core.callbacks import BaseCallbackHandler

    from news_dashboard.ai_client import ManagedPrompt

    captured: dict[str, Any] = {}

    def answer(prompt_value: Any, config: Any) -> AIMessage:
        captured["config"] = config
        return AIMessage(content='[{"name": "OpenAI", "type": "org"}]')

    @contextmanager
    def attributes(**kwargs: Any) -> Generator[None]:
        captured["attributes"] = kwargs
        yield

    callback = BaseCallbackHandler()
    managed = MagicMock(name="managed-prompt")
    model: RunnableLambda[Any, AIMessage] = RunnableLambda(answer)
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_chat_model", return_value=model),
        patch("news_dashboard.ai_client.langfuse_enabled", return_value=True),
        patch(
            "news_dashboard.ai_client.get_prompt",
            return_value=ManagedPrompt(text="Extract entities", langfuse_prompt=managed),
        ),
        patch("langfuse.langchain.CallbackHandler", return_value=callback),
        patch("langfuse.propagate_attributes", side_effect=attributes),
    ):
        result = extract_entities(
            {"id": 1, "title": "OpenAI ships", "summary": "News", "body": "Body"},
            user_id=17,
        )

    assert result == [{"name": "OpenAI", "type": "org"}]
    assert captured["attributes"] == {
        "user_id": "17",
        "tags": ["entities"],
        "trace_name": "entity-extraction",
        "prompt": managed,
    }
    assert captured["config"]["callbacks"].handlers == [callback]


def test_extract_entity_relationships_calls_llm_with_bounded_entities() -> None:
    model = _mock_llm(
        json.dumps(
            [
                {
                    "source_name": "OpenAI",
                    "source_type": "org",
                    "target_name": "Sam Altman",
                    "target_type": "person",
                    "relationship_type": "led_by",
                    "label": "led by",
                    "confidence": 0.8,
                }
            ]
        )
    )
    entities = [{"name": "OpenAI", "type": "org"}, {"name": "Sam Altman", "type": "person"}]

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_chat_model", return_value=model),
    ):
        result = extract_entity_relationships(
            {"id": 1, "title": "OpenAI", "summary": "Sam Altman leads OpenAI.", "body": None},
            entities,
        )

    assert result == [
        {
            "source_name": "OpenAI",
            "source_type": "org",
            "target_name": "Sam Altman",
            "target_type": "person",
            "relationship_type": "led_by",
            "label": "led by",
            "confidence": 0.8,
        }
    ]
    assert len(model.calls) == 1


# ── get_or_extract_entities ───────────────────────────────────────────────────


def test_get_or_extract_entities_returns_cached_without_api_call(pg_clean: str) -> None:
    cached = _entities_json(("OpenAI", "org"))
    article_id = _seed_article(pg_clean, url_slug="cached", title="T", entities=cached)

    model = _mock_llm("[]")
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_chat_model", return_value=model),
    ):
        result = get_or_extract_entities(article_id, database_url=pg_clean)

    assert result == [{"name": "OpenAI", "type": "org"}]
    assert model.calls == []


def test_get_or_extract_entities_extracts_and_caches_when_missing(pg_clean: str) -> None:
    article_id = _seed_article(pg_clean, url_slug="fresh", title="OpenAI ships a model")

    model = _mock_llm('[{"name": "OpenAI", "type": "org"}]')
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_chat_model", return_value=model),
    ):
        first = get_or_extract_entities(article_id, database_url=pg_clean)
        second = get_or_extract_entities(article_id, database_url=pg_clean)

    assert first == [{"name": "OpenAI", "type": "org"}]
    assert second == first
    assert len(model.calls) == 1

    with connect(database_url=pg_clean) as conn:
        row = conn.execute("SELECT entities FROM articles WHERE id = %s", (article_id,)).fetchone()
    stored = json.loads(row["entities"])
    assert stored["v"] == 1
    assert stored["entities"] == [{"name": "OpenAI", "type": "org"}]


def test_get_or_extract_entities_syncs_fresh_entities_to_graph_store(pg_clean: str) -> None:
    article_id = _seed_article(pg_clean, url_slug="graph-fresh", title="OpenAI ships a model")
    synced: list[tuple[dict[str, Any], list[dict[str, str]]]] = []

    class FakeGraphStore:
        def sync_article_entities(
            self, *, article: dict[str, Any], entities: list[dict[str, str]]
        ) -> None:
            synced.append((article, entities))

    model = _mock_llm('[{"name": "OpenAI", "type": "org"}]')
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("news_dashboard.ai_client.get_chat_model", return_value=model),
        patch("news_dashboard.entities.graph_store_from_env", return_value=FakeGraphStore()),
    ):
        result = get_or_extract_entities(article_id, database_url=pg_clean)

    assert result == [{"name": "OpenAI", "type": "org"}]
    assert len(synced) == 1
    article, entities = synced[0]
    assert article["id"] == article_id
    assert article["title"] == "OpenAI ships a model"
    assert article["url"] == "https://ent-src.example/graph-fresh"
    assert entities == [{"name": "OpenAI", "type": "org"}]


def test_get_or_extract_entities_invisible_article_returns_empty(pg_clean: str) -> None:
    owner_id = _seed_user(pg_clean, "ent-owner")
    other_id = _seed_user(pg_clean, "ent-other")
    _seed_source(pg_clean, "ent-private", owner_user_id=owner_id)
    article_id = _seed_article(
        pg_clean,
        slug="ent-private",
        url_slug="priv",
        title="Private",
        entities=_entities_json(("Secret Corp", "org")),
    )

    assert get_or_extract_entities(article_id, user_id=other_id, database_url=pg_clean) == []
    assert get_or_extract_entities(article_id, user_id=owner_id, database_url=pg_clean) == [
        {"name": "Secret Corp", "type": "org"}
    ]


# ── extract_missing_entities ──────────────────────────────────────────────────


def test_extract_missing_entities_respects_limit_and_survives_failures(pg_clean: str) -> None:
    for idx in range(4):
        _seed_article(pg_clean, url_slug=f"m-{idx}", title=f"Article {idx}")

    calls: list[int] = []

    def fake_extract(article: dict[str, Any], user_id: int | None = None) -> list[dict[str, str]]:
        calls.append(int(article["id"]))
        if len(calls) == 1:
            msg = "transient failure"
            raise RuntimeError(msg)
        return [{"name": "OpenAI", "type": "org"}]

    with patch("news_dashboard.entities.extract_entities", side_effect=fake_extract):
        extracted = extract_missing_entities(limit=3, database_url=pg_clean)

    assert len(calls) == 3
    assert extracted == 2

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM articles WHERE entities IS NOT NULL"
        ).fetchone()
    assert row["n"] == 2


def test_sync_cached_entities_to_graph_backfills_valid_cached_rows(pg_clean: str) -> None:
    cached_id = _seed_article(
        pg_clean,
        url_slug="graph-cached",
        title="Cached",
        entities=_entities_json(("OpenAI", "org")),
    )
    _seed_article(pg_clean, url_slug="graph-pending", title="Pending")
    _seed_article(pg_clean, url_slug="graph-invalid", title="Invalid", entities="not json")
    synced: list[tuple[int, list[dict[str, str]]]] = []

    class FakeGraphStore:
        def sync_article_entities(
            self, *, article: dict[str, Any], entities: list[dict[str, str]]
        ) -> None:
            synced.append((int(article["id"]), entities))

    with patch("news_dashboard.entities.graph_store_from_env", return_value=FakeGraphStore()):
        count = sync_cached_entities_to_graph(limit=10, database_url=pg_clean)

    assert count == 1
    assert synced == [(cached_id, [{"name": "OpenAI", "type": "org"}])]


def test_sync_cached_entities_to_graph_skips_when_graph_disabled(pg_clean: str) -> None:
    _seed_article(
        pg_clean,
        url_slug="graph-disabled",
        title="Cached",
        entities=_entities_json(("OpenAI", "org")),
    )

    with patch("news_dashboard.entities.graph_store_from_env", return_value=None):
        assert sync_cached_entities_to_graph(limit=10, database_url=pg_clean) == 0


def test_extract_missing_entity_relationships_writes_to_graph(pg_clean: str) -> None:
    article_id = _seed_article(
        pg_clean,
        url_slug="graph-rels",
        title="Relationships",
        entities=_entities_json(("OpenAI", "org"), ("Sam Altman", "person")),
    )
    synced: list[tuple[int, list[dict[str, Any]]]] = []

    class FakeGraphStore:
        def sync_entity_relationships(
            self, *, article_id: int, relationships: list[dict[str, Any]]
        ) -> None:
            synced.append((article_id, relationships))

    relationships = [
        {
            "source_name": "OpenAI",
            "source_type": "org",
            "target_name": "Sam Altman",
            "target_type": "person",
            "relationship_type": "led_by",
            "label": "led by",
            "confidence": 0.8,
        }
    ]
    with (
        patch("news_dashboard.entities.graph_store_from_env", return_value=FakeGraphStore()),
        patch("news_dashboard.entities.extract_entity_relationships", return_value=relationships),
    ):
        count = extract_missing_entity_relationships(limit=10, database_url=pg_clean)

    assert count == 1
    assert synced == [(article_id, relationships)]
    with connect(database_url=pg_clean) as conn:
        row = conn.execute("SELECT entities FROM articles WHERE id = %s", (article_id,)).fetchone()
    payload = json.loads(row["entities"])
    assert payload["relationships_v"] == 1
    assert payload["relationships"] == relationships


def test_extract_missing_entity_relationships_reuses_cached_relationships(
    pg_clean: str,
) -> None:
    cached_relationships = [
        {
            "source_name": "OpenAI",
            "source_type": "org",
            "target_name": "Sam Altman",
            "target_type": "person",
            "relationship_type": "led_by",
            "label": "led by",
            "confidence": 0.8,
        }
    ]
    article_id = _seed_article(
        pg_clean,
        url_slug="graph-rels-cached",
        title="Relationships",
        entities=json.dumps(
            {
                "v": 1,
                "entities": [
                    {"name": "OpenAI", "type": "org"},
                    {"name": "Sam Altman", "type": "person"},
                ],
                "relationships_v": 1,
                "relationships": cached_relationships,
            }
        ),
    )
    synced: list[tuple[int, list[dict[str, Any]]]] = []

    class FakeGraphStore:
        def sync_entity_relationships(
            self, *, article_id: int, relationships: list[dict[str, Any]]
        ) -> None:
            synced.append((article_id, relationships))

    with (
        patch("news_dashboard.entities.graph_store_from_env", return_value=FakeGraphStore()),
        patch("news_dashboard.entities.extract_entity_relationships") as extracted,
    ):
        count = extract_missing_entity_relationships(limit=10, database_url=pg_clean)

    assert count == 1
    assert synced == [(article_id, cached_relationships)]
    extracted.assert_not_called()


def test_extract_missing_entity_relationships_marks_empty_results(pg_clean: str) -> None:
    article_id = _seed_article(
        pg_clean,
        url_slug="graph-rels-empty",
        title="Relationships",
        entities=_entities_json(("OpenAI", "org"), ("Sam Altman", "person")),
    )

    class FakeGraphStore:
        def sync_entity_relationships(
            self, *, article_id: int, relationships: list[dict[str, Any]]
        ) -> None:
            assert article_id
            assert relationships == []
            msg = "empty relationship results should not sync"
            raise AssertionError(msg)

    with (
        patch("news_dashboard.entities.graph_store_from_env", return_value=FakeGraphStore()),
        patch("news_dashboard.entities.extract_entity_relationships", return_value=[]) as extracted,
    ):
        count = extract_missing_entity_relationships(limit=10, database_url=pg_clean)

    assert count == 0
    extracted.assert_called_once()
    with connect(database_url=pg_clean) as conn:
        row = conn.execute("SELECT entities FROM articles WHERE id = %s", (article_id,)).fetchone()
    payload = json.loads(row["entities"])
    assert payload["relationships_v"] == 1
    assert payload["relationships"] == []


def test_extract_missing_entity_relationships_skips_when_graph_disabled(pg_clean: str) -> None:
    _seed_article(
        pg_clean,
        url_slug="graph-rels-disabled",
        title="Relationships",
        entities=_entities_json(("OpenAI", "org"), ("Sam Altman", "person")),
    )

    with patch("news_dashboard.entities.graph_store_from_env", return_value=None):
        assert extract_missing_entity_relationships(limit=10, database_url=pg_clean) == 0


# ── knowledge_graph ───────────────────────────────────────────────────────────


def test_knowledge_graph_empty_corpus(pg_clean: str) -> None:
    result = knowledge_graph(database_url=pg_clean)
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["pending_count"] == 0


def test_knowledge_graph_builds_nodes_edges_and_article_refs(pg_clean: str) -> None:
    a1 = _seed_article(
        pg_clean,
        url_slug="g1",
        title="OpenAI and Altman",
        entities=_entities_json(("OpenAI", "org"), ("Sam Altman", "person")),
    )
    a2 = _seed_article(
        pg_clean,
        url_slug="g2",
        title="OpenAI and Altman again",
        entities=_entities_json(("OpenAI", "org"), ("Sam Altman", "person")),
    )
    a3 = _seed_article(
        pg_clean,
        url_slug="g3",
        title="OpenAI alone",
        entities=_entities_json(("OpenAI", "org")),
    )
    _seed_article(pg_clean, url_slug="g4", title="Pending extraction")

    result = knowledge_graph(database_url=pg_clean)

    nodes = {n["name"]: n for n in result["nodes"]}
    assert nodes["OpenAI"]["type"] == "org"
    assert nodes["OpenAI"]["count"] == 3
    assert nodes["Sam Altman"]["count"] == 2
    assert set(nodes["OpenAI"]["article_ids"]) == {a1, a2, a3}

    assert len(result["edges"]) == 1
    edge = result["edges"][0]
    assert edge["weight"] == 2
    assert set(edge["article_ids"]) == {a1, a2}
    assert {edge["source"], edge["target"]} == {nodes["OpenAI"]["id"], nodes["Sam Altman"]["id"]}

    titles = {a["id"]: a["title"] for a in result["articles"]}
    assert titles[a1] == "OpenAI and Altman"
    assert result["pending_count"] == 1
    assert result["article_count"] == 4


def test_knowledge_graph_truncates_to_max_nodes(pg_clean: str) -> None:
    pairs = [(f"Entity {i}", "org") for i in range(6)]
    _seed_article(pg_clean, url_slug="t1", title="Many entities", entities=_entities_json(*pairs))
    result = knowledge_graph(database_url=pg_clean, max_nodes=3)
    assert len(result["nodes"]) == 3


def test_knowledge_graph_scopes_to_user_visible_articles(pg_clean: str) -> None:
    user_id = _seed_user(pg_clean, "kg-user")
    other_id = _seed_user(pg_clean, "kg-other")
    _seed_source(pg_clean, "kg-global")
    _seed_source(pg_clean, "kg-other-private", owner_user_id=other_id)

    _seed_article(
        pg_clean,
        slug="kg-global",
        url_slug="vis",
        title="Visible",
        entities=_entities_json(("OpenAI", "org")),
    )
    _seed_article(
        pg_clean,
        slug="kg-other-private",
        url_slug="hid",
        title="Hidden",
        entities=_entities_json(("Secret Corp", "org")),
    )

    result = knowledge_graph(user_id=user_id, database_url=pg_clean)
    names = {n["name"] for n in result["nodes"]}
    assert "OpenAI" in names
    assert "Secret Corp" not in names


def test_knowledge_graph_uses_graph_store_for_visible_article_ids(pg_clean: str) -> None:
    user_id = _seed_user(pg_clean, "kg-neo4j")
    other_id = _seed_user(pg_clean, "kg-neo4j-other")
    _seed_source(pg_clean, "kg-neo4j-global")
    _seed_source(pg_clean, "kg-neo4j-private", owner_user_id=other_id)
    visible_id = _seed_article(
        pg_clean,
        slug="kg-neo4j-global",
        url_slug="visible",
        title="Visible",
        entities=_entities_json(("OpenAI", "org")),
    )
    pending_id = _seed_article(
        pg_clean,
        slug="kg-neo4j-global",
        url_slug="pending",
        title="Pending",
    )
    _seed_article(
        pg_clean,
        slug="kg-neo4j-private",
        url_slug="hidden",
        title="Hidden",
        entities=_entities_json(("Secret Corp", "org")),
    )
    calls: list[dict[str, Any]] = []

    class FakeGraphStore:
        def knowledge_graph(
            self,
            *,
            articles: list[dict[str, Any]],
            pending_count: int,
            days: int,
            max_nodes: int,
        ) -> dict[str, Any]:
            calls.append(
                {
                    "articles": articles,
                    "pending_count": pending_count,
                    "days": days,
                    "max_nodes": max_nodes,
                }
            )
            return {
                "nodes": [{"id": "org:openai", "name": "OpenAI", "type": "org", "count": 1}],
                "edges": [],
                "articles": [{"id": visible_id, "title": "Visible"}],
                "article_count": len(articles),
                "pending_count": pending_count,
                "days": days,
                "graph_store": "neo4j",
            }

    with patch("news_dashboard.entities.graph_store_from_env", return_value=FakeGraphStore()):
        result = knowledge_graph(user_id=user_id, days=14, max_nodes=5, database_url=pg_clean)

    assert result["graph_store"] == "neo4j"
    assert result["article_count"] == 2
    assert calls[0]["pending_count"] == 1
    assert calls[0]["days"] == 14
    assert calls[0]["max_nodes"] == 5
    assert {article["id"] for article in calls[0]["articles"]} == {visible_id, pending_id}
