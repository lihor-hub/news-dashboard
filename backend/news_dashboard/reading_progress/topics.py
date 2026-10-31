"""Versioned subject attribution, independent of feed/user tags and mutable taxonomy."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

TAXONOMY_VERSION = 1
RULE_VERSION = 1
LEVELS = (
    (1, "Explorer"),
    (10, "Enthusiast"),
    (30, "Regular"),
    (100, "Trailblazer"),
    (250, "Pathfinder"),
)
BREADTH_TARGETS = (3, 5, 10)
# Each tuple is one subject concept: synonyms cannot supply two summary hits.
TRACKS = {
    "python": (
        "Python",
        (("python", "python programming"), ("pypi",), ("mypy",), ("pyright",), ("ruff",)),
    ),
    "large_language_models": (
        "Large language models",
        (
            ("llm", "llms", "large language model", "large language models"),
            ("retrieval augmented generation", "retrieval-augmented generation"),
            ("qwen weights", "qwen3.5"),
        ),
    ),
    "ai_agents": (
        "AI agents",
        (
            (
                "ai agent",
                "ai agents",
                "ai coding agent",
                "ai coding agents",
                "openai agents",
                "agentic",
                "agentic ai",
            ),
            ("multi-agent", "multi agent"),
            ("langgraph",),
            ("langchain",),
            ("model context protocol",),
        ),
    ),
    "ai_research": (
        "AI research",
        (
            ("machine learning",),
            ("neural network", "neural networks"),
            ("deep learning",),
            ("reinforcement learning",),
            ("interpretability research",),
            ("model internal mechanisms", "claude's internal mechanisms"),
            ("learning machines",),
            ("multimodal large language model", "multimodal large language models"),
        ),
    ),
    "cloud_infrastructure": (
        "Cloud infrastructure",
        (
            ("kubernetes", "k8s"),
            ("docker",),
            ("podman",),
            ("terraform",),
            ("cloud infrastructure",),
        ),
    ),
    "security": (
        "Security",
        (
            ("cybersecurity", "cyber security"),
            ("vulnerability", "vulnerabilities"),
            ("exploit", "exploits"),
            ("cve",),
            ("security incident", "security update"),
            ("backdoor", "backdoors"),
            ("breach", "breached"),
            ("hardening guidance",),
        ),
    ),
    "data_engineering": (
        "Data engineering",
        (
            ("data pipeline", "data pipelines"),
            ("data engineering",),
            ("data warehouse", "data warehouses"),
            ("apache spark",),
        ),
    ),
    "web_development": (
        "Web development",
        (
            ("web development",),
            ("web browser", "web browsers"),
            ("web platform",),
            ("css",),
            ("html",),
        ),
    ),
    "javascript_typescript": (
        "JavaScript & TypeScript",
        (("javascript",), ("typescript", "typescripting"), ("ecmascript",), ("node.js", "nodejs")),
    ),
    "software_engineering": (
        "Software engineering",
        (
            ("software architecture",),
            ("software engineering",),
            ("refactoring",),
            ("distributed system", "distributed systems"),
        ),
    ),
    "ruby": ("Ruby", (("ruby", "ruby programming"), ("rubygems",), ("ruby on rails",))),
}
ALIASES = {
    "python": ("python", "python programming"),
    "large_language_models": ("llm", "llms", "large language models", "ai-llm"),
    "ai_agents": ("agents", "ai agents", "agentic ai"),
    "ai_research": ("ai-research", "ai research", "machine learning research"),
    "cloud_infrastructure": ("infra", "cloud-infra", "cloud infrastructure"),
    "security": ("security", "cybersecurity", "cyber security"),
    "data_engineering": ("data engineering", "data-engineering"),
    "web_development": ("web", "web development"),
    "javascript_typescript": ("javascript", "typescript", "javascript/typescript"),
    "software_engineering": ("engineering", "software engineering"),
    "ruby": ("ruby", "ruby programming"),
}


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def canonical_topic(label: str) -> str | None:
    """Label normalization is for interoperability, never eligibility evidence."""
    normalized = normalize(label)
    return next((topic for topic, aliases in ALIASES.items() if normalized in aliases), None)


_PATTERNS = {
    topic: tuple(
        re.compile(r"(?<!\w)(?:" + "|".join(re.escape(term) for term in terms) + r")(?!\w)")
        for terms in concepts
    )
    for topic, (_, concepts) in TRACKS.items()
}


def classify(title: str, summary: str) -> list[dict[str, Any]]:
    """Title evidence outranks two distinct summary concepts, then stable ID; cap two."""
    title, summary = normalize(title), normalize(summary)
    matches = []
    text = title + " " + summary
    for topic, patterns in _PATTERNS.items():
        # Domain vocabulary cannot veto explicit programming-subject evidence.
        if (
            topic == "python"
            and re.search(r"\b(?:snakes?|reptiles?)\b", text)
            and not re.search(r"\bpython programming\b", text)
            and not any(pattern.search(text) for pattern in patterns[1:])
        ):
            continue
        if (
            topic == "ruby"
            and re.search(r"\b(?:minerals?|corundum|gemstones?)\b", text)
            and not re.search(r"\bruby (?:programming|vm)\b", text)
            and not any(pattern.search(text) for pattern in patterns[1:])
        ):
            continue
        title_hit = any(pattern.search(title) for pattern in patterns)
        # Bare Node needs JavaScript ecosystem context, not graph/botanical node mentions.
        if topic == "javascript_typescript" and re.search(r"\bnode\b", title):
            title_hit = title_hit or any(pattern.search(summary) for pattern in patterns)
        summary_hits = sum(bool(pattern.search(summary)) for pattern in patterns)
        if title_hit or summary_hits >= 2:
            matches.append(
                {"topic_id": topic, "evidence_code": "title" if title_hit else "summary"}
            )
    return sorted(
        matches, key=lambda match: (match["evidence_code"] != "title", match["topic_id"])
    )[:2]


def topic_key(topic: str, target: int) -> str:
    return f"topic_{topic}_{target}"


def reward_topic(key: str) -> str | None:
    return next((topic for topic in TRACKS for n, _ in LEVELS if key == topic_key(topic, n)), None)


def finalize_topics(conn: Any, credit_id: int, title: str, summary: str) -> None:
    """Caller holds account lock; freeze even zero without retaining source text."""
    row = conn.execute(
        "SELECT topics_finalized_version FROM user_read_credits WHERE id=%s", (credit_id,)
    ).fetchone()
    if row["topics_finalized_version"] is not None:
        return
    # A transitional source, if present, takes precedence over later mutable article text.
    source = conn.execute(
        "SELECT title,summary FROM user_read_credit_sources WHERE credit_id=%s", (credit_id,)
    ).fetchone()
    if source:
        title, summary = source["title"], source["summary"]
    for match in classify(title, summary):
        conn.execute(
            """INSERT INTO user_topic_credits(
               credit_id,topic_id,taxonomy_version,rule_version,evidence_code)
               VALUES (%s,%s,%s,%s,%s)""",
            (credit_id, match["topic_id"], TAXONOMY_VERSION, RULE_VERSION, match["evidence_code"]),
        )
    conn.execute(
        """UPDATE user_read_credits SET topics_finalized_version=%s,
           topics_taxonomy_version=%s WHERE id=%s""",
        (RULE_VERSION, TAXONOMY_VERSION, credit_id),
    )
    conn.execute("DELETE FROM user_read_credit_sources WHERE credit_id=%s", (credit_id,))


def topic_counts(conn: Any, user_id: int) -> dict[str, int]:
    return {
        row["topic_id"]: row["n"]
        for row in conn.execute(
            """SELECT t.topic_id,COUNT(*) AS n FROM user_topic_credits t
               JOIN user_read_credits c ON c.id=t.credit_id
               WHERE c.user_id=%s GROUP BY t.topic_id""",
            (user_id,),
        ).fetchall()
    }


def candidates(conn: Any, user_id: int) -> list[dict[str, Any]]:
    counts = topic_counts(conn, user_id)
    result = [
        {"key": topic_key(topic, n), "criteria_version": 1, "progress": count, "target": n}
        for topic, count in counts.items()
        for n, _ in LEVELS
        if count >= n
    ]
    breadth = sum(count >= 3 for count in counts.values())
    return result + [
        {"key": f"breadth_{n}", "criteria_version": 1, "progress": breadth, "target": n}
        for n in BREADTH_TARGETS
        if breadth >= n
    ]


def snapshot(conn: Any, user_id: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = topic_counts(conn, user_id)
    by_key = {item["key"]: item for item in items}
    tracks: list[dict[str, Any]] = []
    for topic, (name, _) in TRACKS.items():
        count = counts.get(topic, 0)
        level = next((name for n, name in reversed(LEVELS) if count >= n), None)
        next_level = next(((n, name) for n, name in LEVELS if count < n), None)
        tracks.append(
            {
                "id": topic,
                "name": name,
                "count": count,
                "level": level,
                "next_target": next_level[0] if next_level else None,
                "next_level": next_level[1] if next_level else None,
                "earned_levels": [
                    by_key[topic_key(topic, n)]
                    for n, _ in LEVELS
                    if by_key[topic_key(topic, n)]["unlocked"]
                ],
            }
        )
    tracks.sort(key=lambda track: (-track["count"], track["id"]))
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "rule_version": RULE_VERSION,
        "attribution_cap": 2,
        "tracks": tracks,
        "top_track_ids": [track["id"] for track in tracks if track["count"] > 0][:3],
        "breadth_count": sum(count >= 3 for count in counts.values()),
    }
