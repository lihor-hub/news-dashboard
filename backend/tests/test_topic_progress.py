from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest

from news_dashboard.db import connect
from news_dashboard.reading_progress import credits, daily, rewards, topics  # noqa: A004

pytestmark = pytest.mark.postgres


@pytest.fixture
def topic_account(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    with connect() as conn:
        return int(
            conn.execute(
                "INSERT INTO users(username,password_hash) VALUES ('topic-reader','x') RETURNING id"
            ).fetchone()["id"]
        )


def test_aliases_are_not_eligibility() -> None:
    for topic, aliases in topics.ALIASES.items():
        for alias in aliases:
            assert topics.canonical_topic(f"  {alias.upper()}  ") == topic
    assert topics.canonical_topic("\uff30\uff39\uff34\uff28\uff2f\uff2e") == "python"
    assert topics.canonical_topic("developer-tools") is None
    assert topics.classify("A release", "agents workflow data metrics update pip uv AI") == []
    assert topics.classify("A title", "Python python programming") == []
    assert topics.classify("A title", "Python and PyPI") == [
        {"topic_id": "python", "evidence_code": "summary"}
    ]
    assert topics.classify("Pythonic rubylike", "one Python mention") == []
    assert topics.classify("\uff30\uff39\uff34\uff28\uff2f\uff2e", "") == [
        {"topic_id": "python", "evidence_code": "title"}
    ]


def test_literal_subject_ambiguity_and_refined_evidence() -> None:
    assert topics.classify("Farmed Python snake meat", "") == []
    assert topics.classify("Ruby", "Ruby is a variety of the mineral corundum") == []
    assert topics.classify("GemStone's Ruby VM", "") == [
        {"topic_id": "ruby", "evidence_code": "title"}
    ]
    for title, topic in (
        ("Python and PyPI tooling for modeling snake meat production", "python"),
        ("Ruby on Rails database for mineral corundum", "ruby"),
        ("Python programming to model reptiles", "python"),
        ("RubyGems tools for gemstone catalogs", "ruby"),
    ):
        assert topics.classify(title, "") == [{"topic_id": topic, "evidence_code": "title"}]
    assert topics.classify("Python reptile habitat", "") == []
    assert topics.classify("Ruby mineral deposits", "") == []
    for title in ("Open source AI coding agent", "OpenAI agents"):
        assert topics.classify(title, "")[0]["topic_id"] == "ai_agents"
    for title in (
        "Security incident",
        "Backdoor in an extension",
        "Platform breached",
        "Hardening guidance",
    ):
        assert topics.classify(title, "")[0]["topic_id"] == "security"
    assert topics.classify("Internal mechanisms of a diesel engine", "") == []


def test_javascript_inflection_and_contextual_node() -> None:
    expected = [{"topic_id": "javascript_typescript", "evidence_code": "title"}]
    assert topics.classify("TypeScripting an interview", "") == expected
    assert topics.classify("Moving from Node", "A JavaScript stack comparison") == expected
    assert topics.classify("Node graph traversal", "") == []
    assert topics.classify("Node growth", "Botanical research") == []
    assert topics.classify("Typescriptish syntax", "") == []


def test_development_corpus_numeric_gate_not_independent_approval() -> None:
    import json
    from pathlib import Path

    corpus = json.loads((Path(__file__).parent / "fixtures/topic_calibration_v1.json").read_text())
    rows = corpus["articles"]
    assert len(rows) == len({row["url"] for row in rows}) == 100
    selected = true_positive = 0
    for row in rows:
        actual = {match["topic_id"] for match in topics.classify(row["title"], row["summary"])}
        selected += len(actual)
        true_positive += len(actual & set(row["gold_topics"]))
    assert true_positive / selected >= 0.95
    for topic in topics.TRACKS:
        positives = [row for row in rows if topic in row["gold_topics"]]
        assert len(positives) >= 5
        assert any(topic in row["near_miss_for"] for row in rows)
        hits = sum(
            topic in {m["topic_id"] for m in topics.classify(row["title"], row["summary"])}
            for row in positives
        )
        assert hits / len(positives) >= 0.8, topic


def test_rank_cap_and_distinct_concepts() -> None:
    assert [r["topic_id"] for r in topics.classify("Ruby Python CSS", "")] == ["python", "ruby"]
    assert [r["topic_id"] for r in topics.classify("Ruby", "Python PyPI; CSS HTML")] == [
        "ruby",
        "python",
    ]
    assert topics.classify("A title", "k8s Kubernetes") == []


def test_first_credit_atomic_group_zero_and_freeze(topic_account: int) -> None:
    uid = topic_account
    with connect() as conn:
        daily.lock_account(conn, uid)
        result = credits.credit_read(
            conn, uid, url="https://topic.test/one", title="Python Ruby CSS"
        )
        assert set(result["newly_unlocked"]) == {
            "articles_read_1",
            "topic_python_1",
            "topic_ruby_1",
        }
        rows = conn.execute("SELECT * FROM user_achievements").fetchall()
        assert {str(r["reward_group_id"]) for r in rows} == {result["reward_group_id"]}
        assert len({r["earned_at"] for r in rows}) == 1
        credits.credit_read(conn, uid, url="https://topic.test/one", title="Kubernetes")
        credits.credit_read(conn, uid, url="https://topic.test/zero")
        credits.credit_read(conn, uid, url="https://topic.test/zero", title="Python")
        assert topics.topic_counts(conn, uid) == {"python": 1, "ruby": 1}
        assert {
            r["topics_finalized_version"] for r in conn.execute("SELECT * FROM user_read_credits")
        } == {1}
        assert not conn.execute("SELECT * FROM user_read_credit_sources").fetchall()
    state = rewards.daily_collection(uid)
    assert state["reading_total"] == 2
    assert state["topics"]["top_track_ids"] == ["python", "ruby"]
    assert len(state["topics"]["tracks"]) == 11


@pytest.mark.parametrize("count", [0, 1, 7, 9, 10, 29, 30, 99, 100, 249, 250, 251, 1000])
def test_ladder_unbounded(topic_account: int, count: int) -> None:
    uid = topic_account
    with connect() as conn:
        daily.lock_account(conn, uid)
        # Real credits, including classifier, predicates, permanent dates and one group per cause.
        for n in range(count):
            credits.credit_read(conn, uid, url=f"https://level.test/{n}", title="Python")
    state = rewards.daily_collection(uid)
    track = next(t for t in state["topics"]["tracks"] if t["id"] == "python")
    assert track["count"] == count
    expected = [(n, level) for n, level in topics.LEVELS if n <= count]
    assert track["level"] == (expected[-1][1] if expected else None)
    assert len(track["earned_levels"]) == len(expected)
    assert track["next_target"] == next((n for n, _ in topics.LEVELS if n > count), None)
    with connect() as conn:
        before = conn.execute("SELECT * FROM user_achievements ORDER BY achievement_key").fetchall()
        daily.lock_account(conn, uid)
        credits.credit_read(conn, uid, url="https://level.test/0", title="Ruby")
        if count:
            assert (
                conn.execute("SELECT * FROM user_achievements ORDER BY achievement_key").fetchall()
                == before
            )


def test_breadth_permanent_and_import_silent(topic_account: int) -> None:
    uid = topic_account
    titles = [
        "Python",
        "LLM",
        "AI agents",
        "machine learning",
        "Kubernetes",
        "vulnerability",
        "data engineering",
        "CSS",
        "TypeScript",
        "software engineering",
        "Ruby",
    ]
    with connect() as conn:
        daily.lock_account(conn, uid)
        for i, title in enumerate(titles):
            for n in range(3):
                credits.credit_read(
                    conn,
                    uid,
                    url=f"https://breadth.test/{i}/{n}",
                    title=title,
                    origin="import",
                    method="import",
                )
            earned = {r["achievement_key"] for r in conn.execute("SELECT * FROM user_achievements")}
            assert {f"breadth_{n}" for n in topics.BREADTH_TARGETS if n <= i + 1} == {
                key for key in earned if key.startswith("breadth_")
            }
        assert not conn.execute("SELECT * FROM user_reward_groups").fetchall()
        assert all(r["earned_at"] is None for r in conn.execute("SELECT * FROM user_achievements"))
    assert rewards.daily_collection(uid)["topics"]["breadth_count"] == 11


def test_read_promotion_and_breadth_cross_in_one_cause(topic_account: int) -> None:
    uid = topic_account
    with connect() as conn:
        daily.lock_account(conn, uid)
        for title, total in (("Python", 9), ("Ruby", 3), ("CSS", 2), ("", 35)):
            for n in range(total):
                credits.credit_read(
                    conn,
                    uid,
                    url=f"https://combined.test/{title}/{n}",
                    title=title,
                    method="import",
                    origin="import",
                )
        result = credits.credit_read(
            conn, uid, url="https://combined.test/live", title="Python CSS"
        )
        assert set(result["newly_unlocked"]) == {"articles_read_50", "topic_python_10", "breadth_3"}
        rows = conn.execute("SELECT * FROM user_achievements WHERE origin='live'").fetchall()
        assert {str(row["reward_group_id"]) for row in rows} == {result["reward_group_id"]}
        assert len({row["earned_at"] for row in rows}) == 1
        assert conn.execute("SELECT COUNT(*) AS n FROM user_reward_groups").fetchone()["n"] == 1


def test_crossing_concurrency_and_rollback(topic_account: int) -> None:
    uid = topic_account
    with connect() as conn:
        daily.lock_account(conn, uid)
        for n in range(9):
            credits.credit_read(conn, uid, url=f"https://race.test/{n}", title="Python")
    barrier = Barrier(2)

    def write(n: int) -> dict[str, Any]:
        barrier.wait()
        with connect() as conn:
            daily.lock_account(conn, uid)
            return credits.credit_read(conn, uid, url=f"https://race.test/live{n}", title="Python")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [1, 2]))
    assert sum("topic_python_10" in r["newly_unlocked"] for r in results) == 1
    with connect() as conn:
        assert topics.topic_counts(conn, uid) == {"python": 11}
    with pytest.raises(RuntimeError), connect() as conn:  # noqa: PT012 - transaction rollback
        daily.lock_account(conn, uid)
        credits.credit_read(conn, uid, url="https://rollback.test", title="Ruby")
        msg = "rollback"
        raise RuntimeError(msg)
    with connect() as conn:
        assert topics.topic_counts(conn, uid) == {"python": 11}
        daily.lock_account(conn, uid)
        conn.execute("DELETE FROM users WHERE id=%s", (uid,))
        assert not conn.execute("SELECT * FROM user_topic_credits").fetchall()


def test_transitional_source_consumed_not_mutable_text(topic_account: int) -> None:
    uid = topic_account
    with connect() as conn:
        daily.lock_account(conn, uid)
        credit_id = conn.execute(
            """INSERT INTO user_read_credits(
                 user_id,identity_digest,origin,method,recorded_at,effective_at)
               VALUES (%s,%s,'live','manual',clock_timestamp(),clock_timestamp()) RETURNING id""",
            (uid, credits.identity_digest("https://transition.test")),
        ).fetchone()["id"]
        conn.execute("INSERT INTO user_read_credit_sources VALUES (%s,'Python','')", (credit_id,))
        topics.finalize_topics(conn, credit_id, "Ruby", "")
        assert topics.topic_counts(conn, uid) == {"python": 1}
        assert not conn.execute("SELECT * FROM user_read_credit_sources").fetchall()
        topics.finalize_topics(conn, credit_id, "Ruby", "")
        assert topics.topic_counts(conn, uid) == {"python": 1}


def test_api_export_isolation_and_read_only(topic_account: int) -> None:
    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.export import assemble_user_export
    from news_dashboard.main import app

    uid = topic_account
    with connect() as conn:
        daily.lock_account(conn, uid)
        credits.credit_read(conn, uid, url="https://mine.test", title="Python")
        other = conn.execute(
            "INSERT INTO users(username,password_hash) VALUES ('other-topic','x') RETURNING id"
        ).fetchone()["id"]
        daily.lock_account(conn, other)
        credits.credit_read(conn, other, url="https://other.test", title="Ruby")
    assert len(assemble_user_export(uid)["progress"]["topic_credits"]) == 1
    assert assemble_user_export(uid)["progress"]["topic_credits"][0]["topic_id"] == "python"
    app.dependency_overrides[require_auth] = lambda: {"id": uid, "is_guest": False}
    try:
        with TestClient(app) as client:
            first = client.get("/api/users/me/progress-rewards")
            assert first.status_code == 200
            second = client.get("/api/users/me/progress-rewards")
            assert first.json() == second.json()
            assert first.json()["topics"]["top_track_ids"] == ["python"]
            response = client.get("/api/users/me/progress-rewards?user_id=" + str(other))
            assert response.json() == first.json()
    finally:
        app.dependency_overrides.clear()
    with TestClient(app) as client:
        assert client.get("/api/users/me/progress-rewards").status_code == 401
    with connect() as conn:
        daily.lock_account(conn, uid)
        conn.execute("DELETE FROM users WHERE id=%s", (uid,))
        assert topics.topic_counts(conn, other) == {"ruby": 1}
        assert conn.execute("SELECT COUNT(*) AS n FROM user_topic_credits").fetchone()["n"] == 1
