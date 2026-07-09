"""Optional Neo4j boundary for knowledge-graph storage."""

from __future__ import annotations

import importlib
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol, cast

logger = logging.getLogger(__name__)

_ENTITY_TYPES = frozenset({"person", "org", "product", "place"})
_DEFAULT_DATABASE = "neo4j"


class GraphUnavailableError(Exception):
    """Raised when Neo4j is configured incorrectly or cannot be reached."""


class GraphResult(Protocol):
    def single(self) -> dict[str, Any] | None: ...

    def data(self) -> list[dict[str, Any]]: ...


class GraphSession(Protocol):
    def __enter__(self) -> GraphSession: ...

    def __exit__(self, *_args: object) -> None: ...

    def run(self, query: str, **params: Any) -> GraphResult: ...


class GraphDriver(Protocol):
    def session(self, **kwargs: Any) -> GraphSession: ...

    def verify_connectivity(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class GraphConfig:
    uri: str
    username: str
    password: str
    database: str = _DEFAULT_DATABASE


def graph_config_from_env() -> GraphConfig | None:
    """Read optional Neo4j settings from the process environment."""
    uri = os.getenv("NEO4J_URI", "").strip()
    if not uri:
        return None

    username = os.getenv("NEO4J_USER", "").strip()
    password = os.getenv("NEO4J_PASSWORD", "").strip()
    missing = [
        name
        for name, value in (("NEO4J_USER", username), ("NEO4J_PASSWORD", password))
        if not value
    ]
    if missing:
        joined = ", ".join(missing)
        msg = f"Neo4j is configured with NEO4J_URI but missing {joined}"
        raise GraphUnavailableError(msg)

    database = os.getenv("NEO4J_DATABASE", "").strip() or _DEFAULT_DATABASE
    return GraphConfig(uri=uri, username=username, password=password, database=database)


def _entity_id(name: str, entity_type: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{entity_type}:{slug}"


def _confidence(value: Any) -> float:
    try:
        confidence = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _normalize_entities(entities: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entity in entities:
        name = str(entity.get("name") or "").strip()
        entity_type = str(entity.get("type") or "").strip().lower()
        if not name or entity_type not in _ENTITY_TYPES:
            continue
        key = (name.lower(), entity_type)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"id": _entity_id(name, entity_type), "name": name, "type": entity_type})
    return normalized


def _normalize_relationships(relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for relationship in relationships:
        source_name = str(relationship.get("source_name") or "").strip()
        source_type = str(relationship.get("source_type") or "").strip().lower()
        target_name = str(relationship.get("target_name") or "").strip()
        target_type = str(relationship.get("target_type") or "").strip().lower()
        relationship_type = str(relationship.get("relationship_type") or "").strip().lower()
        label = str(relationship.get("label") or relationship_type.replace("_", " ")).strip()
        if (
            not source_name
            or not target_name
            or not relationship_type
            or source_type not in _ENTITY_TYPES
            or target_type not in _ENTITY_TYPES
        ):
            continue
        source_id = _entity_id(source_name, source_type)
        target_id = _entity_id(target_name, target_type)
        key = (source_id, target_id, relationship_type)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "relationship_type": relationship_type,
                "label": label,
                "confidence": _confidence(relationship.get("confidence")),
            }
        )
    return normalized


class GraphStore:
    """Small Neo4j client wrapper with a fakeable driver for unit tests."""

    def __init__(self, config: GraphConfig, driver: GraphDriver | None = None) -> None:
        self.config = config
        self._driver = driver

    @property
    def driver(self) -> GraphDriver:
        if self._driver is None:
            try:
                neo4j = importlib.import_module("neo4j")
            except ImportError as exc:
                msg = "Neo4j support requires the neo4j Python package"
                raise GraphUnavailableError(msg) from exc
            self._driver = cast(
                "GraphDriver",
                neo4j.GraphDatabase.driver(
                    self.config.uri,
                    auth=(self.config.username, self.config.password),
                ),
            )
        return self._driver

    def verify_connectivity(self) -> bool:
        self.driver.verify_connectivity()
        return True

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()

    def sync_article_entities(
        self,
        *,
        article: dict[str, Any],
        entities: list[dict[str, str]],
    ) -> None:
        """Upsert an Article node, Entity nodes, and MENTIONS relationships."""
        normalized = _normalize_entities(entities)
        article_id = int(article["id"])
        query = """
        MERGE (article:Article {id: $article_id})
        SET article.title = $title,
            article.url = $url,
            article.source_slug = $source_slug,
            article.discovered_at = $discovered_at
        WITH article
        UNWIND $entities AS entity_row
        MERGE (entity:Entity {id: entity_row.id})
        SET entity.name = entity_row.name,
            entity.type = entity_row.type
        MERGE (article)-[mention:MENTIONS]->(entity)
        ON CREATE SET mention.created_at = datetime()
        SET mention.updated_at = datetime()
        """
        with self.driver.session(database=self.config.database) as session:
            session.run(
                query,
                article_id=article_id,
                title=str(article.get("title") or ""),
                url=str(article.get("url") or ""),
                source_slug=str(article.get("source_slug") or ""),
                discovered_at=str(article.get("discovered_at") or ""),
                entities=normalized,
            )

    def sync_entity_relationships(
        self,
        *,
        article_id: int,
        relationships: list[dict[str, Any]],
    ) -> None:
        """Upsert typed entity relationships with article provenance."""
        normalized = _normalize_relationships(relationships)
        if not normalized:
            return
        query = """
        UNWIND $relationships AS relationship
        MATCH (source:Entity {id: relationship.source_id})
        MATCH (target:Entity {id: relationship.target_id})
        MERGE (source)-[edge:RELATED_TO {
          article_id: $article_id,
          relationship_type: relationship.relationship_type
        }]->(target)
        SET edge.article_id = $article_id,
            edge.label = relationship.label,
            edge.confidence = relationship.confidence,
            edge.updated_at = datetime()
        ON CREATE SET edge.created_at = datetime()
        """
        with self.driver.session(database=self.config.database) as session:
            session.run(query, article_id=article_id, relationships=normalized)

    def knowledge_graph(
        self,
        *,
        articles: list[dict[str, Any]],
        pending_count: int,
        days: int,
        max_nodes: int,
    ) -> dict[str, Any]:
        """Build the API graph response from Neo4j for already-visible articles."""
        article_ids = [int(article["id"]) for article in articles]
        if not article_ids:
            return {
                "nodes": [],
                "edges": [],
                "articles": [],
                "article_count": 0,
                "pending_count": pending_count,
                "days": days,
                "graph_store": "neo4j",
            }

        query = """
        MATCH (article:Article)-[:MENTIONS]->(entity:Entity)
        WHERE article.id IN $article_ids
        WITH entity,
             count(DISTINCT article) AS mentions,
             collect(DISTINCT article.id) AS entity_articles
        ORDER BY mentions DESC, entity.name ASC
        LIMIT $max_nodes
        WITH collect({
          id: entity.id,
          name: entity.name,
          type: entity.type,
          count: mentions,
          article_ids: entity_articles
        }) AS nodes
        WITH nodes, [node IN nodes | node.id] AS node_ids
        CALL {
          WITH node_ids
          MATCH (a:Article)-[:MENTIONS]->(source:Entity)
          MATCH (a)-[:MENTIONS]->(target:Entity)
          WHERE a.id IN $article_ids
            AND source.id IN node_ids
            AND target.id IN node_ids
            AND source.id < target.id
          WITH source,
               target,
               count(DISTINCT a) AS weight,
               collect(DISTINCT a.id) AS edge_articles
          RETURN collect({
            source: source.id,
            target: target.id,
            weight: weight,
            article_ids: edge_articles,
            kind: 'cooccurrence',
            label: 'co-mentioned'
          }) AS cooccurrence_edges
        }
        CALL {
          WITH node_ids
          MATCH (source:Entity)-[relationship:RELATED_TO]->(target:Entity)
          WHERE relationship.article_id IN $article_ids
            AND source.id IN node_ids
            AND target.id IN node_ids
          RETURN collect({
            source: source.id,
            target: target.id,
            weight: 1,
            article_ids: [relationship.article_id],
            kind: 'typed',
            relationship_type: relationship.relationship_type,
            label: relationship.label,
            confidence: relationship.confidence
          }) AS typed_edges
        }
        RETURN nodes, cooccurrence_edges + typed_edges AS edges
        """
        with self.driver.session(database=self.config.database) as session:
            row = session.run(query, article_ids=article_ids, max_nodes=max_nodes).single()

        nodes = list(row.get("nodes", [])) if row is not None else []
        edges = list(row.get("edges", [])) if row is not None else []
        titles = {int(article["id"]): str(article.get("title") or "") for article in articles}
        return {
            "nodes": nodes,
            "edges": edges,
            "articles": [
                {"id": article_id, "title": titles[article_id]} for article_id in article_ids
            ],
            "article_count": len(articles),
            "pending_count": pending_count,
            "days": days,
            "graph_store": "neo4j",
        }

    def ask_context(self, *, article_ids: list[int], max_items: int = 8) -> dict[str, Any] | None:
        """Return bounded graph context for already-authorized Ask AI source articles."""
        if not article_ids:
            return None
        query = """
        MATCH (article:Article)-[:MENTIONS]->(entity:Entity)
        WHERE article.id IN $article_ids
        WITH collect(DISTINCT {
          id: entity.id,
          name: entity.name,
          type: entity.type,
          article_ids: [article.id]
        })[0..$max_items] AS entities
        OPTIONAL MATCH (source:Entity)-[edge:RELATED_TO]->(target:Entity)
        WHERE edge.article_id IN $article_ids
        RETURN entities,
               collect({
                 source: source.id,
                 source_name: source.name,
                 target: target.id,
                 target_name: target.name,
                 relationship_type: edge.relationship_type,
                 label: edge.label,
                 confidence: edge.confidence,
                 article_ids: [edge.article_id]
               })[0..$max_items] AS relationships
        """
        with self.driver.session(database=self.config.database) as session:
            row = session.run(query, article_ids=article_ids, max_items=max_items).single()
        if row is None:
            return None
        return {
            "entities": list(row.get("entities", [])),
            "relationships": [
                relationship
                for relationship in list(row.get("relationships", []))
                if relationship.get("source") and relationship.get("target")
            ],
        }


def graph_store_from_env() -> GraphStore | None:
    config = graph_config_from_env()
    if config is None:
        return None
    return GraphStore(config)
