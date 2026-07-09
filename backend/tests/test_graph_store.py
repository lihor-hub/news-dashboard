"""Tests for the optional Neo4j graph storage boundary."""

from __future__ import annotations

from typing import Any

import pytest

from news_dashboard.graph_store import (
    GraphConfig,
    GraphStore,
    GraphUnavailableError,
    graph_config_from_env,
)

_TEST_GRAPH_CREDENTIAL = "credential-for-tests"


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def data(self) -> list[dict[str, Any]]:
        return self._rows


class FakeSession:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def run(self, query: str, **params: Any) -> FakeResult:
        self.calls.append((query, params))
        return FakeResult(self.rows)


class FakeDriver:
    def __init__(self, session: FakeSession) -> None:
        self.session_obj = session
        self.verified = False
        self.closed = False

    def session(self, **_kwargs: Any) -> FakeSession:
        return self.session_obj

    def verify_connectivity(self) -> None:
        self.verified = True

    def close(self) -> None:
        self.closed = True


def test_graph_config_from_env_is_disabled_without_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    assert graph_config_from_env() is None


def test_graph_config_from_env_reads_connection_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", _TEST_GRAPH_CREDENTIAL)
    monkeypatch.setenv("NEO4J_DATABASE", "news")

    assert graph_config_from_env() == GraphConfig(
        uri="bolt://neo4j:7687",
        username="neo4j",
        password=_TEST_GRAPH_CREDENTIAL,
        database="news",
    )


def test_graph_config_from_env_rejects_partial_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    with pytest.raises(GraphUnavailableError, match="NEO4J_PASSWORD"):
        graph_config_from_env()


def test_graph_store_verifies_connectivity_and_closes_driver() -> None:
    session = FakeSession()
    driver = FakeDriver(session)
    store = GraphStore(
        GraphConfig(
            uri="bolt://neo4j:7687",
            username="neo4j",
            password=_TEST_GRAPH_CREDENTIAL,
        ),
        driver=driver,
    )

    assert store.verify_connectivity() is True
    store.close()

    assert driver.verified is True
    assert driver.closed is True


def test_graph_store_syncs_article_entities_idempotently() -> None:
    session = FakeSession()
    driver = FakeDriver(session)
    store = GraphStore(
        GraphConfig(
            uri="bolt://neo4j:7687",
            username="neo4j",
            password=_TEST_GRAPH_CREDENTIAL,
        ),
        driver=driver,
    )

    store.sync_article_entities(
        article={
            "id": 42,
            "title": "OpenAI ships",
            "url": "https://example.test/openai",
            "source_slug": "tech",
            "discovered_at": "2026-07-09T00:00:00Z",
        },
        entities=[
            {"name": "OpenAI", "type": "org"},
            {"name": "OpenAI", "type": "org"},
            {"name": "Sam Altman", "type": "person"},
        ],
    )

    assert len(session.calls) == 1
    query, params = session.calls[0]
    assert "MERGE (article:Article {id: $article_id})" in query
    assert "MERGE (entity:Entity {id: entity_row.id})" in query
    assert "MERGE (article)-[mention:MENTIONS]->(entity)" in query
    assert params["article_id"] == 42
    assert params["title"] == "OpenAI ships"
    assert params["entities"] == [
        {"id": "org:openai", "name": "OpenAI", "type": "org"},
        {"id": "person:sam-altman", "name": "Sam Altman", "type": "person"},
    ]


def test_graph_store_syncs_typed_relationships_with_article_provenance() -> None:
    session = FakeSession()
    driver = FakeDriver(session)
    store = GraphStore(
        GraphConfig(
            uri="bolt://neo4j:7687",
            username="neo4j",
            password=_TEST_GRAPH_CREDENTIAL,
        ),
        driver=driver,
    )

    store.sync_entity_relationships(
        article_id=42,
        relationships=[
            {
                "source_name": "OpenAI",
                "source_type": "org",
                "target_name": "Sam Altman",
                "target_type": "person",
                "relationship_type": "led_by",
                "label": "led by",
                "confidence": 0.8,
            }
        ],
    )

    assert len(session.calls) == 1
    query, params = session.calls[0]
    assert "MATCH (source:Entity {id: relationship.source_id})" in query
    assert "MERGE (source)-[edge:RELATED_TO" in query
    assert "edge.article_id = $article_id" in query
    assert params["article_id"] == 42
    assert params["relationships"] == [
        {
            "source_id": "org:openai",
            "target_id": "person:sam-altman",
            "relationship_type": "led_by",
            "label": "led by",
            "confidence": 0.8,
        }
    ]


def test_graph_store_coerces_malformed_relationship_confidence() -> None:
    session = FakeSession()
    store = GraphStore(
        GraphConfig(
            uri="bolt://neo4j:7687",
            username="neo4j",
            password=_TEST_GRAPH_CREDENTIAL,
        ),
        driver=FakeDriver(session),
    )

    store.sync_entity_relationships(
        article_id=42,
        relationships=[
            {
                "source_name": "OpenAI",
                "source_type": "org",
                "target_name": "Sam Altman",
                "target_type": "person",
                "relationship_type": "led_by",
                "confidence": "not-a-number",
            }
        ],
    )

    assert session.calls[0][1]["relationships"][0]["confidence"] == 0.0


def test_graph_store_builds_response_from_visible_articles() -> None:
    session = FakeSession(
        [
            {
                "nodes": [
                    {
                        "id": "org:openai",
                        "name": "OpenAI",
                        "type": "org",
                        "count": 2,
                        "article_ids": [1, 2],
                    }
                ],
                "edges": [
                    {
                        "source": "org:openai",
                        "target": "person:sam-altman",
                        "weight": 1,
                        "article_ids": [1],
                        "kind": "cooccurrence",
                        "label": "co-mentioned",
                    },
                    {
                        "source": "org:openai",
                        "target": "person:sam-altman",
                        "weight": 1,
                        "article_ids": [1],
                        "kind": "typed",
                        "relationship_type": "led_by",
                        "label": "led by",
                        "confidence": 0.8,
                    },
                ],
            }
        ]
    )
    store = GraphStore(
        GraphConfig(
            uri="bolt://neo4j:7687",
            username="neo4j",
            password=_TEST_GRAPH_CREDENTIAL,
        ),
        driver=FakeDriver(session),
    )

    result = store.knowledge_graph(
        articles=[{"id": 1, "title": "One"}, {"id": 2, "title": "Two"}],
        pending_count=3,
        days=7,
        max_nodes=40,
    )

    assert result == {
        "nodes": [
            {
                "id": "org:openai",
                "name": "OpenAI",
                "type": "org",
                "count": 2,
                "article_ids": [1, 2],
            }
        ],
        "edges": [
            {
                "source": "org:openai",
                "target": "person:sam-altman",
                "weight": 1,
                "article_ids": [1],
                "kind": "cooccurrence",
                "label": "co-mentioned",
            },
            {
                "source": "org:openai",
                "target": "person:sam-altman",
                "weight": 1,
                "article_ids": [1],
                "kind": "typed",
                "relationship_type": "led_by",
                "label": "led by",
                "confidence": 0.8,
            },
        ],
        "articles": [{"id": 1, "title": "One"}, {"id": 2, "title": "Two"}],
        "article_count": 2,
        "pending_count": 3,
        "days": 7,
        "graph_store": "neo4j",
    }

    query, params = session.calls[0]
    assert "MATCH (article:Article)-[:MENTIONS]->(entity:Entity)" in query
    assert "MATCH (source:Entity)-[relationship:RELATED_TO]->(target:Entity)" in query
    assert params["article_ids"] == [1, 2]
    assert params["max_nodes"] == 40


def test_graph_store_ask_context_includes_relationship_display_names() -> None:
    session = FakeSession(
        [
            {
                "entities": [
                    {"id": "org:openai", "name": "OpenAI", "type": "org", "article_ids": [1]}
                ],
                "relationships": [
                    {
                        "source": "org:openai",
                        "source_name": "OpenAI",
                        "target": "person:sam-altman",
                        "target_name": "Sam Altman",
                        "relationship_type": "led_by",
                        "label": "led by",
                        "article_ids": [1],
                    }
                ],
            }
        ]
    )
    store = GraphStore(
        GraphConfig(
            uri="bolt://neo4j:7687",
            username="neo4j",
            password=_TEST_GRAPH_CREDENTIAL,
        ),
        driver=FakeDriver(session),
    )

    context = store.ask_context(article_ids=[1], max_items=5)

    assert context == {
        "entities": [{"id": "org:openai", "name": "OpenAI", "type": "org", "article_ids": [1]}],
        "relationships": [
            {
                "source": "org:openai",
                "source_name": "OpenAI",
                "target": "person:sam-altman",
                "target_name": "Sam Altman",
                "relationship_type": "led_by",
                "label": "led by",
                "article_ids": [1],
            }
        ],
    }
    query, params = session.calls[0]
    assert "source_name: source.name" in query
    assert "target_name: target.name" in query
    assert params["article_ids"] == [1]
    assert params["max_items"] == 5
