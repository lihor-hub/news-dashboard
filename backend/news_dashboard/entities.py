"""LLM-backed named-entity extraction and the news knowledge graph.

Entities (people, orgs, products, places) are extracted once per article via
the free-LLM gateway and cached in ``articles.entities`` as JSON
``{"v": 1, "entities": [{"name", "type"}]}`` — mirroring how ``insights``
caches its bullets. ``knowledge_graph()`` aggregates the cached entities only
and never invokes the LLM, so the endpoint stays fast and free; a scheduler
job (``entity_extraction``) fills the cache in the background.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from news_dashboard.db import connect, init_db
from news_dashboard.graph_store import GraphUnavailableError, graph_store_from_env

logger = logging.getLogger(__name__)

DEFAULT_ENTITIES_MODEL = "gpt-4o-mini"
ENTITIES_CACHE_VERSION = 1
RELATIONSHIPS_CACHE_VERSION = 1
_ENTITY_TYPES = frozenset({"person", "org", "product", "place"})
_MAX_TEXT_CHARS = 4_000
_MAX_ENTITIES_PER_ARTICLE = 10
_MAX_RELATIONSHIPS_PER_ARTICLE = 12
_MAX_GRAPH_ARTICLES = 300
_PROMPT = (
    "Extract the named entities from the news article below. "
    "Return ONLY a JSON array (no prose, no code fences) of at most "
    f"{_MAX_ENTITIES_PER_ARTICLE} objects, each shaped "
    '{"name": "<canonical short name>", "type": "<person|org|product|place>"}. '
    "Use the most canonical short form of each name (e.g. 'OpenAI', not "
    "'OpenAI, Inc.'). Only include entities that are clearly mentioned in the "
    "article text; do not invent or infer entities from general knowledge."
)
_RELATIONSHIP_PROMPT = (
    "Extract explicit relationships between the provided named entities from the news article. "
    "Return ONLY a JSON array (no prose, no code fences) of at most "
    f"{_MAX_RELATIONSHIPS_PER_ARTICLE} objects, each shaped "
    '{"source_name": "...", "source_type": "person|org|product|place", '
    '"target_name": "...", "target_type": "person|org|product|place", '
    '"relationship_type": "short_snake_case", "label": "human readable", '
    '"confidence": 0.0}. Only include relationships directly supported by the article text. '
    "Do not infer relationships from general knowledge."
)


class EntitiesNotConfiguredError(Exception):
    """Raised when no AI key is configured for entity extraction."""


def _entities_ai_config() -> tuple[str, str | None, str]:
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        msg = "FREE_LLM_API_KEY (or OPENAI_API_KEY) is not configured"
        raise EntitiesNotConfiguredError(msg)
    model = os.getenv("OPENAI_ENTITIES_MODEL", DEFAULT_ENTITIES_MODEL)
    return api_key, base_url, model


def _build_text(article: dict[str, Any]) -> str:
    parts = [
        str(article.get("title") or ""),
        str(article.get("summary") or ""),
        str(article.get("body") or ""),
    ]
    return "\n\n".join(p for p in parts if p.strip())[:_MAX_TEXT_CHARS]


def _parse_entities(response_text: str) -> list[dict[str, str]]:
    """Parse the model response into a validated, deduplicated entity list."""
    text = response_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()

    try:
        raw = json.loads(text)
    except ValueError:
        return []
    if not isinstance(raw, list):
        return []

    entities: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        entity_type = str(item.get("type") or "").strip().lower()
        if not name or entity_type not in _ENTITY_TYPES:
            continue
        key = (name.lower(), entity_type)
        if key in seen:
            continue
        seen.add(key)
        entities.append({"name": name, "type": entity_type})
        if len(entities) >= _MAX_ENTITIES_PER_ARTICLE:
            break
    return entities


def _json_text(response_text: str) -> str:
    text = response_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    return text


def _confidence(value: Any) -> float:
    try:
        confidence = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _parse_relationships(
    response_text: str,
    entities: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Parse, validate, and dedupe model-extracted entity relationships."""
    entity_lookup = {
        (str(entity.get("name") or "").lower(), str(entity.get("type") or "").lower()): (
            str(entity.get("name") or "").strip(),
            str(entity.get("type") or "").strip().lower(),
        )
        for entity in entities
        if str(entity.get("name") or "").strip()
        and str(entity.get("type") or "").strip().lower() in _ENTITY_TYPES
    }
    try:
        raw = json.loads(_json_text(response_text))
    except ValueError:
        return []
    if not isinstance(raw, list):
        return []

    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        source_key = (
            str(item.get("source_name") or "").strip().lower(),
            str(item.get("source_type") or "").strip().lower(),
        )
        target_key = (
            str(item.get("target_name") or "").strip().lower(),
            str(item.get("target_type") or "").strip().lower(),
        )
        source = entity_lookup.get(source_key)
        target = entity_lookup.get(target_key)
        relationship_type = str(item.get("relationship_type") or "").strip().lower()
        label = str(item.get("label") or relationship_type.replace("_", " ")).strip()
        if source is None or target is None or not relationship_type:
            continue
        dedupe_key = (source[0].lower(), target[0].lower(), relationship_type)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        confidence = _confidence(item.get("confidence"))
        relationships.append(
            {
                "source_name": source[0],
                "source_type": source[1],
                "target_name": target[0],
                "target_type": target[1],
                "relationship_type": relationship_type,
                "label": label,
                "confidence": confidence,
            }
        )
        if len(relationships) >= _MAX_RELATIONSHIPS_PER_ARTICLE:
            break
    return relationships


def extract_entities(article: dict[str, Any], user_id: int | None = None) -> list[dict[str, str]]:
    """Call the LLM and return the extracted entity list.

    Raises EntitiesNotConfiguredError when no AI key is configured.
    """
    api_key, base_url, model = _entities_ai_config()

    text = _build_text(article)
    if not text.strip():
        return []

    from langchain_core.prompts import ChatPromptTemplate
    from langfuse import propagate_attributes

    from news_dashboard.ai_client import get_chat_model, get_prompt, langfuse_enabled, response_text

    prompt = get_prompt("entity-extraction", fallback=_PROMPT)
    logger.info("Extracting entities for article %s", article.get("id"))
    chat_model = get_chat_model(api_key=api_key, base_url=base_url, model=model, max_tokens=512)
    callbacks: list[Any] = []
    if langfuse_enabled():
        from langfuse.langchain import CallbackHandler

        callbacks.append(CallbackHandler())
    template = ChatPromptTemplate.from_messages([("human", "{instruction}\n\n{text}")])
    with propagate_attributes(
        user_id=str(user_id) if user_id is not None else None,
        tags=["entities"],
        trace_name="entity-extraction",
        prompt=prompt.langfuse_prompt,
    ):
        result = (template | chat_model).invoke(
            {"instruction": prompt.text, "text": text}, config={"callbacks": callbacks}
        )
    response = response_text(result).strip()
    entities = _parse_entities(response)
    logger.info("Entities extracted for article %s: %d entities", article.get("id"), len(entities))
    return entities


def extract_entity_relationships(
    article: dict[str, Any],
    entities: list[dict[str, str]],
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """Call the LLM for explicit relationships between already-extracted entities."""
    if len(entities) < 2:
        return []
    api_key, base_url, model = _entities_ai_config()
    text = _build_text(article)
    if not text.strip():
        return []

    from langchain_core.prompts import ChatPromptTemplate
    from langfuse import propagate_attributes

    from news_dashboard.ai_client import get_chat_model, get_prompt, langfuse_enabled, response_text

    prompt = get_prompt("entity-relationship-extraction", fallback=_RELATIONSHIP_PROMPT)
    entity_text = json.dumps(entities)
    chat_model = get_chat_model(api_key=api_key, base_url=base_url, model=model, max_tokens=768)
    callbacks: list[Any] = []
    if langfuse_enabled():
        from langfuse.langchain import CallbackHandler

        callbacks.append(CallbackHandler())
    template = ChatPromptTemplate.from_messages(
        [("human", "{instruction}\n\nEntities:\n{entities}\n\nArticle:\n{text}")]
    )
    with propagate_attributes(
        user_id=str(user_id) if user_id is not None else None,
        tags=["entities", "relationships"],
        trace_name="entity-relationship-extraction",
        prompt=prompt.langfuse_prompt,
    ):
        result = (template | chat_model).invoke(
            {"instruction": prompt.text, "entities": entity_text, "text": text},
            config={"callbacks": callbacks},
        )
    return _parse_relationships(response_text(result).strip(), entities)


def _decode_cached_payload(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _decode_cached(raw: str | None) -> list[dict[str, str]] | None:
    payload = _decode_cached_payload(raw)
    if payload is None:
        return None
    entities = payload.get("entities")
    if not isinstance(entities, list):
        return None
    return [e for e in entities if isinstance(e, dict)]


def _decode_cached_relationships(raw: str | None) -> list[dict[str, Any]] | None:
    payload = _decode_cached_payload(raw)
    if payload is None or payload.get("relationships_v") != RELATIONSHIPS_CACHE_VERSION:
        return None
    relationships = payload.get("relationships")
    if not isinstance(relationships, list):
        return []
    return [relationship for relationship in relationships if isinstance(relationship, dict)]


def _close_graph_store(graph_store: Any) -> None:
    close = getattr(graph_store, "close", None)
    if callable(close):
        close()


def _sync_entities_to_graph(article: dict[str, Any], entities: list[dict[str, str]]) -> bool:
    try:
        graph_store = graph_store_from_env()
    except GraphUnavailableError:
        logger.exception("Neo4j graph store is configured but unavailable")
        return False
    if graph_store is None:
        return False
    try:
        graph_store.sync_article_entities(article=article, entities=entities)
    except Exception:
        logger.exception("Failed to sync article %s entities to Neo4j", article.get("id"))
        return False
    finally:
        _close_graph_store(graph_store)
    return True


def _store_entities(
    article: dict[str, Any],
    entities: list[dict[str, str]],
    database_url: str | None,
) -> None:
    article_id = int(article["id"])
    payload = json.dumps({"v": ENTITIES_CACHE_VERSION, "entities": entities})
    with connect(database_url=database_url) as conn:
        conn.execute("UPDATE articles SET entities = %s WHERE id = %s", (payload, article_id))
    _sync_entities_to_graph(article, entities)


def _store_entity_relationships(
    *,
    article_id: int,
    entities: list[dict[str, str]],
    relationships: list[dict[str, Any]],
    database_url: str | None,
) -> None:
    payload = json.dumps(
        {
            "v": ENTITIES_CACHE_VERSION,
            "entities": entities,
            "relationships_v": RELATIONSHIPS_CACHE_VERSION,
            "relationships": relationships,
        }
    )
    with connect(database_url=database_url) as conn:
        conn.execute("UPDATE articles SET entities = %s WHERE id = %s", (payload, article_id))


def get_or_extract_entities(
    article_id: int,
    user_id: int | None = None,
    database_url: str | None = None,
) -> list[dict[str, str]]:
    """Return cached entities or extract + cache them.

    When user_id is provided the article must be visible to that user.
    Returns [] for invisible or non-existent articles.
    """
    init_db(database_url=database_url)

    with connect(database_url=database_url) as conn:
        if user_id is not None:
            row = conn.execute(
                """
                SELECT a.id, a.url, a.title, a.source_slug, a.summary, a.body,
                       a.entities, a.discovered_at
                FROM articles a
                JOIN sources src ON src.slug = a.source_slug
                LEFT JOIN user_sources us_src
                  ON us_src.source_slug = a.source_slug AND us_src.user_id = %s
                WHERE a.id = %s AND (
                  (src.owner_user_id IS NULL AND COALESCE(us_src.enabled, TRUE))
                  OR src.owner_user_id = %s
                )
                """,
                (user_id, article_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, url, title, source_slug, summary, body, entities, discovered_at
                FROM articles
                WHERE id = %s
                """,
                (article_id,),
            ).fetchone()

    if row is None:
        return []

    cached = _decode_cached(row["entities"])
    if cached is not None:
        return cached

    entities = extract_entities(dict(row), user_id=user_id)
    _store_entities(dict(row), entities, database_url)
    return entities


def extract_missing_entities(
    limit: int = 25,
    days: int = 7,
    database_url: str | None = None,
) -> int:
    """Extract entities for up to ``limit`` recent articles lacking them.

    Per-article failures are logged and skipped so one bad article does not
    starve the batch. Returns the number of articles successfully extracted.
    """
    init_db(database_url=database_url)

    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT id, url, title, source_slug, summary, body, discovered_at
            FROM articles
            WHERE discovered_at::timestamptz >= NOW() - INTERVAL '1 day' * %s
              AND entities IS NULL
            ORDER BY discovered_at DESC
            LIMIT %s
            """,
            (days, limit),
        ).fetchall()

    extracted = 0
    for row in rows:
        try:
            entities = extract_entities(dict(row))
        except EntitiesNotConfiguredError:
            raise
        except Exception:
            logger.exception("Entity extraction failed for article %s", row["id"])
            continue
        _store_entities(dict(row), entities, database_url)
        extracted += 1
    return extracted


def sync_cached_entities_to_graph(
    limit: int = 250,
    days: int = 30,
    database_url: str | None = None,
) -> int:
    """Backfill cached PostgreSQL entity JSON into Neo4j when graph storage is enabled."""
    init_db(database_url=database_url)
    try:
        graph_store = graph_store_from_env()
    except GraphUnavailableError:
        logger.exception("Neo4j graph store is configured but unavailable")
        return 0
    if graph_store is None:
        return 0

    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT id, url, title, source_slug, entities, discovered_at
            FROM articles
            WHERE discovered_at::timestamptz >= NOW() - INTERVAL '1 day' * %s
              AND entities IS NOT NULL
            ORDER BY discovered_at DESC
            LIMIT %s
            """,
            (days, limit),
        ).fetchall()

    synced = 0
    try:
        for row in rows:
            entities = _decode_cached(row["entities"])
            if entities is None:
                continue
            try:
                graph_store.sync_article_entities(article=dict(row), entities=entities)
            except Exception:
                logger.exception("Failed to backfill article %s entities to Neo4j", row["id"])
                continue
            synced += 1
        return synced
    finally:
        _close_graph_store(graph_store)


def extract_missing_entity_relationships(
    limit: int = 50,
    days: int = 7,
    database_url: str | None = None,
) -> int:
    """Extract typed entity relationships for cached articles and sync them to Neo4j."""
    init_db(database_url=database_url)
    try:
        graph_store = graph_store_from_env()
    except GraphUnavailableError:
        logger.exception("Neo4j graph store is configured but unavailable")
        return 0
    if graph_store is None:
        return 0

    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT id, title, summary, body, entities
            FROM articles
            WHERE discovered_at::timestamptz >= NOW() - INTERVAL '1 day' * %s
              AND entities IS NOT NULL
            ORDER BY discovered_at DESC
            LIMIT %s
            """,
            (days, limit),
        ).fetchall()

    synced = 0
    try:
        for row in rows:
            article_id = int(row["id"])
            entities = _decode_cached(row["entities"])
            if entities is None or len(entities) < 2:
                continue

            cached_relationships = _decode_cached_relationships(row["entities"])
            if cached_relationships is None:
                try:
                    relationships = extract_entity_relationships(dict(row), entities)
                except EntitiesNotConfiguredError:
                    logger.warning("Skipping entity relationship extraction; AI is not configured")
                    return synced
                except Exception:
                    logger.exception(
                        "Entity relationship extraction failed for article %s",
                        row["id"],
                    )
                    continue
                _store_entity_relationships(
                    article_id=article_id,
                    entities=entities,
                    relationships=relationships,
                    database_url=database_url,
                )
            else:
                relationships = cached_relationships

            if not relationships:
                continue
            try:
                graph_store.sync_entity_relationships(
                    article_id=article_id,
                    relationships=relationships,
                )
            except Exception:
                logger.exception("Failed to sync article %s relationships to Neo4j", row["id"])
                continue
            synced += 1
        return synced
    finally:
        _close_graph_store(graph_store)


def _entity_id(name: str, entity_type: str) -> str:
    return f"{entity_type}:{name.lower().replace(' ', '-')}"


def _visible_graph_rows(
    *,
    user_id: int | None,
    days: int,
    database_url: str | None,
) -> list[dict[str, Any]]:
    with connect(database_url=database_url) as conn:
        if user_id is None:
            rows = conn.execute(
                """
                SELECT id, title, entities
                FROM articles
                WHERE discovered_at::timestamptz >= NOW() - INTERVAL '1 day' * %s
                ORDER BY discovered_at DESC
                LIMIT %s
                """,
                (days, _MAX_GRAPH_ARTICLES),
            ).fetchall()
            return [dict(row) for row in rows]

        rows = conn.execute(
            """
            SELECT a.id, a.title, a.entities
            FROM articles a
            JOIN sources src ON src.slug = a.source_slug
            LEFT JOIN user_sources us
              ON us.source_slug = src.slug AND us.user_id = %s
            LEFT JOIN user_article_state uas
              ON uas.article_id = a.id AND uas.user_id = %s
            WHERE a.discovered_at::timestamptz >= NOW() - INTERVAL '1 day' * %s
              AND COALESCE(uas.state, 'today') != 'archived'
              AND (
                (
                  src.owner_user_id IS NULL
                  AND COALESCE(us.enabled, TRUE) IS TRUE
                )
                OR (
                  src.owner_user_id = %s
                  AND src.enabled IS TRUE
                )
              )
            ORDER BY a.discovered_at DESC
            LIMIT %s
            """,
            (user_id, user_id, days, user_id, _MAX_GRAPH_ARTICLES),
        ).fetchall()
        return [dict(row) for row in rows]


def _pending_entity_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if _decode_cached(row["entities"]) is None)


def _neo4j_knowledge_graph(
    *,
    rows: list[dict[str, Any]],
    pending_count: int,
    days: int = 7,
    max_nodes: int = 40,
) -> dict[str, Any] | None:
    try:
        graph_store = graph_store_from_env()
    except GraphUnavailableError:
        logger.exception("Neo4j graph store is configured but unavailable")
        return None
    if graph_store is None:
        return None
    try:
        return graph_store.knowledge_graph(
            articles=[{"id": int(row["id"]), "title": str(row["title"] or "")} for row in rows],
            pending_count=pending_count,
            days=days,
            max_nodes=max_nodes,
        )
    except Exception:
        logger.exception("Falling back to PostgreSQL entity cache for knowledge graph")
        return None
    finally:
        _close_graph_store(graph_store)


def _legacy_knowledge_graph(
    *,
    rows: list[dict[str, Any]],
    pending_count: int,
    days: int,
    max_nodes: int,
) -> dict[str, Any]:
    # node key -> {"id", "name", "type", "count", "article_ids"}
    node_map: dict[tuple[str, str], dict[str, Any]] = {}
    # article id -> list of node keys mentioned in it
    mentions: dict[int, list[tuple[str, str]]] = {}
    titles: dict[int, str] = {}

    for row in rows:
        entities = _decode_cached(row["entities"])
        if entities is None:
            continue
        article_id = int(row["id"])
        keys: list[tuple[str, str]] = []
        for entity in entities:
            name = str(entity.get("name") or "").strip()
            entity_type = str(entity.get("type") or "").strip().lower()
            if not name or entity_type not in _ENTITY_TYPES:
                continue
            key = (name.lower(), entity_type)
            if key in keys:
                continue
            keys.append(key)
            node = node_map.setdefault(
                key,
                {
                    "id": _entity_id(name, entity_type),
                    "name": name,
                    "type": entity_type,
                    "count": 0,
                    "article_ids": [],
                },
            )
            node["count"] += 1
            node["article_ids"].append(article_id)
        if keys:
            mentions[article_id] = keys
            titles[article_id] = str(row["title"] or "")

    kept = sorted(node_map.values(), key=lambda n: (-n["count"], n["name"]))[:max_nodes]
    kept_keys = {(n["name"].lower(), n["type"]) for n in kept}
    node_id_by_key = {(n["name"].lower(), n["type"]): n["id"] for n in kept}

    # edge (id_a, id_b) sorted -> {"weight", "article_ids"}
    edge_map: dict[tuple[str, str], dict[str, Any]] = {}
    referenced_articles: set[int] = set()
    for article_id, keys in mentions.items():
        visible = [k for k in keys if k in kept_keys]
        for i in range(len(visible)):
            for j in range(i + 1, len(visible)):
                id_a = node_id_by_key[visible[i]]
                id_b = node_id_by_key[visible[j]]
                edge_key = (id_a, id_b) if id_a < id_b else (id_b, id_a)
                edge = edge_map.setdefault(edge_key, {"weight": 0, "article_ids": []})
                edge["weight"] += 1
                edge["article_ids"].append(article_id)
        if visible:
            referenced_articles.add(article_id)

    edges = [
        {
            "source": source,
            "target": target,
            "weight": data["weight"],
            "article_ids": data["article_ids"],
        }
        for (source, target), data in sorted(edge_map.items(), key=lambda item: -item[1]["weight"])
    ]

    return {
        "nodes": kept,
        "edges": edges,
        "articles": [
            {"id": article_id, "title": titles[article_id]}
            for article_id in sorted(referenced_articles)
        ],
        "article_count": len(rows),
        "pending_count": pending_count,
        "days": days,
    }


def knowledge_graph(
    user_id: int | None = None,
    days: int = 7,
    max_nodes: int = 40,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Aggregate cached entities over recent visible articles into a graph.

    Reads the cache only — never calls the LLM. ``pending_count`` reports how
    many visible recent articles still lack extracted entities so the UI can
    explain a sparse graph.
    """
    init_db(database_url=database_url)

    rows = _visible_graph_rows(user_id=user_id, days=days, database_url=database_url)
    pending_count = _pending_entity_count(rows)
    neo4j_graph = _neo4j_knowledge_graph(
        rows=rows,
        pending_count=pending_count,
        days=days,
        max_nodes=max_nodes,
    )
    if neo4j_graph is not None:
        return neo4j_graph
    return _legacy_knowledge_graph(
        rows=rows,
        pending_count=pending_count,
        days=days,
        max_nodes=max_nodes,
    )
