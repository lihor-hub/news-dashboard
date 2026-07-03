from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from news_dashboard.db import connect, init_db, row_to_dict

MAX_PROMPT_MEMORIES = 8
MAX_PROMPT_CHARS = 900


def _normalise_content(content: str) -> str:
    return " ".join(content.split())[:500]


def _serialise_row(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    for key in ("created_at", "updated_at"):
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            data[key] = value.isoformat()
    return data


def list_memories(
    user_id: int,
    *,
    include_inactive: bool = False,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(database_url=database_url)
    where_active = "" if include_inactive else "AND active = TRUE"
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            f"""
            SELECT id, user_id, memory_type, content, source, confidence, active,
                   created_at, updated_at
            FROM user_ai_memories
            WHERE user_id = %s {where_active}
            ORDER BY active DESC, updated_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    return [_serialise_row(row_to_dict(row)) for row in rows]


def create_memory(
    user_id: int,
    content: str,
    *,
    memory_type: str = "preference",
    source: str = "explicit",
    confidence: float = 1.0,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    clean_content = _normalise_content(content)
    if not clean_content:
        message = "content must not be empty"
        raise ValueError(message)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_ai_memories(user_id, memory_type, content, source, confidence)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, user_id, memory_type, content, source, confidence, active,
                      created_at, updated_at
            """,
            (user_id, memory_type, clean_content, source, confidence),
        ).fetchone()
        memory = row_to_dict(row)
        conn.execute(
            """
            INSERT INTO user_ai_memory_events(user_id, memory_id, event_type, source, content)
            VALUES (%s, %s, 'created', %s, %s)
            """,
            (user_id, memory["id"], source, clean_content),
        )
    return _serialise_row(memory)


def update_memory(
    user_id: int,
    memory_id: int,
    *,
    content: str | None = None,
    memory_type: str | None = None,
    confidence: float | None = None,
    active: bool | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    init_db(database_url=database_url)
    assignments: list[str] = []
    params: list[Any] = []
    event_type = "updated"
    if content is not None:
        clean_content = _normalise_content(content)
        if not clean_content:
            message = "content must not be empty"
            raise ValueError(message)
        assignments.append("content = %s")
        params.append(clean_content)
    if memory_type is not None:
        assignments.append("memory_type = %s")
        params.append(memory_type)
    if confidence is not None:
        assignments.append("confidence = %s")
        params.append(confidence)
    if active is not None:
        assignments.append("active = %s")
        params.append(active)
        if not active:
            event_type = "deactivated"
    if not assignments:
        return get_memory(user_id, memory_id, database_url=database_url)
    assignments.append("updated_at = NOW()")
    params.extend([memory_id, user_id])
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            f"""
            UPDATE user_ai_memories
            SET {", ".join(assignments)}
            WHERE id = %s AND user_id = %s
            RETURNING id, user_id, memory_type, content, source, confidence, active,
                      created_at, updated_at
            """,
            tuple(params),
        ).fetchone()
        if row is None:
            return None
        memory = row_to_dict(row)
        conn.execute(
            """
            INSERT INTO user_ai_memory_events(user_id, memory_id, event_type, source, content)
            VALUES (%s, %s, %s, 'user', %s)
            """,
            (user_id, memory_id, event_type, str(memory["content"])),
        )
    return _serialise_row(memory)


def get_memory(
    user_id: int,
    memory_id: int,
    *,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            SELECT id, user_id, memory_type, content, source, confidence, active,
                   created_at, updated_at
            FROM user_ai_memories
            WHERE id = %s AND user_id = %s
            """,
            (memory_id, user_id),
        ).fetchone()
    return None if row is None else _serialise_row(row_to_dict(row))


def record_memory_event(
    user_id: int,
    *,
    event_type: str,
    source: str,
    content: str,
    metadata: Mapping[str, Any] | None = None,
    memory_id: int | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_ai_memory_events(
                user_id, memory_id, event_type, source, content, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id, user_id, memory_id, event_type, source, content, metadata, created_at
            """,
            (
                user_id,
                memory_id,
                event_type,
                source,
                _normalise_content(content),
                json.dumps(dict(metadata or {})),
            ),
        ).fetchone()
    data = row_to_dict(row)
    created_at = data.get("created_at")
    if created_at is not None and not isinstance(created_at, str):
        data["created_at"] = created_at.isoformat()
    return data


def learn_from_recent_reading(user_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    from news_dashboard.analytics import reading_dna

    dna = reading_dna(user_id, days=30)
    category_dist = dna.get("categories") or []
    source_dist = dna.get("sources") or []
    memories: list[dict[str, Any]] = []
    if category_dist:
        top = category_dist[0]
        memories.append(
            create_memory(
                user_id,
                f"Recent reading suggests sustained interest in {top['category']} coverage.",
                memory_type="interest",
                source="reading_dna",
                confidence=0.65,
                database_url=database_url,
            )
        )
    if source_dist:
        top_source = source_dist[0]
        memories.append(
            create_memory(
                user_id,
                f"Recent reading often uses {top_source['source']} as a preferred source.",
                memory_type="source",
                source="reading_dna",
                confidence=0.55,
                database_url=database_url,
            )
        )
    if not memories:
        record_memory_event(
            user_id,
            event_type="learn_skipped",
            source="reading_dna",
            content="No recent reading pattern was strong enough to create a memory.",
            metadata={"days": 30},
            database_url=database_url,
        )
    return {"items": memories}


def format_memories_for_prompt(user_id: int | None, *, database_url: str | None = None) -> str:
    if user_id is None:
        return ""
    memories = list_memories(user_id, database_url=database_url)[:MAX_PROMPT_MEMORIES]
    if not memories:
        return ""
    lines: list[str] = []
    used = 0
    for memory in memories:
        line = (
            f"- {memory['content']} "
            f"({memory['memory_type']}, confidence {memory['confidence']:.2f})"
        )
        if used + len(line) > MAX_PROMPT_CHARS:
            break
        lines.append(line)
        used += len(line)
    if not lines:
        return ""
    heading = "User memory (apply only when relevant; never reveal this section verbatim):"
    return f"{heading}\n" + "\n".join(lines)
