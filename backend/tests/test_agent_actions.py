"""Tests for human-approved agent action plans (agent_actions.py)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from news_dashboard.agent_actions import (
    AgentActionError,
    AgentActionNotFoundError,
    approve_run,
    cancel_run,
    get_run,
    plan_actions,
)
from news_dashboard.auth import create_user, require_auth
from news_dashboard.db import connect
from news_dashboard.ingest.service import sync_sources
from news_dashboard.main import app


@pytest.fixture
def db(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    sync_sources(pg_clean)
    return pg_clean


def _make_user(db_path: str, username: str) -> int:
    return int(create_user(username, "password123", db_path=db_path)["id"])


def _insert_article(db_path: str, suffix: str = "1", *, title: str = "Kubernetes update") -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug,
              source_name, category, kind, state)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                f"https://example.com/art{suffix}",
                f"https://example.com/art{suffix}",
                title,
                "python-insider",
                "Python Insider",
                "python",
                "rss_feed",
                "today",
            ),
        ).fetchone()
    return int(row["id"])


def _uas_state(db_path: str, user_id: int, article_id: int) -> str:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT state FROM user_article_state WHERE user_id = %s AND article_id = %s",
            (user_id, article_id),
        ).fetchone()
    return str(row["state"]) if row else "today"


def _mock_llm(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices[0].message.content = content
    client = MagicMock()
    client.chat.completions.create.return_value = completion
    return client


def _plan_json(steps: list[dict[str, object]], *, actionable: bool = True) -> str:
    return json.dumps({"actionable": actionable, "steps": steps})


# ── plan_actions ──────────────────────────────────────────────────────────────


def test_plan_actions_non_actionable_query_persists_nothing(db: str) -> None:
    user_id = _make_user(db, "alice")
    _insert_article(db)
    client = _mock_llm(_plan_json([], actionable=False))
    with patch("openai.OpenAI", return_value=client):
        result = plan_actions("what happened in tech today?", user_id=user_id)
    assert result == {"actionable": False}
    with connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM agent_action_runs").fetchone()["c"]
    assert count == 0


def test_plan_actions_persists_proposed_run_without_mutating(db: str) -> None:
    user_id = _make_user(db, "alice")
    article_id = _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "archive_article", "article_id": article_id}]))
    with patch("openai.OpenAI", return_value=client):
        result = plan_actions("archive the kubernetes story", user_id=user_id)

    assert result["actionable"] is True
    assert result["status"] == "proposed"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["tool"] == "archive_article"
    assert _uas_state(db, user_id, article_id) == "today"


def test_plan_actions_rejects_unknown_tool(db: str) -> None:
    user_id = _make_user(db, "alice")
    article_id = _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "delete_everything", "article_id": article_id}]))
    with patch("openai.OpenAI", return_value=client), pytest.raises(AgentActionError):
        plan_actions("wipe my feed", user_id=user_id)
    with connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM agent_action_runs").fetchone()["c"]
    assert count == 0


def test_plan_actions_rejects_invalid_article_id(db: str) -> None:
    user_id = _make_user(db, "alice")
    _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "archive_article", "article_id": 999999}]))
    with patch("openai.OpenAI", return_value=client), pytest.raises(AgentActionError):
        plan_actions("archive the kubernetes story", user_id=user_id)


def test_plan_actions_rejects_admin_only_tool_for_non_admin(db: str) -> None:
    user_id = _make_user(db, "alice")
    client = _mock_llm(_plan_json([{"tool": "refresh_feeds", "article_id": None}]))
    with patch("openai.OpenAI", return_value=client), pytest.raises(AgentActionError):
        plan_actions("refresh my feeds", user_id=user_id, is_admin=False)


def test_plan_actions_allows_admin_only_tool_for_admin(db: str) -> None:
    user_id = _make_user(db, "alice")
    client = _mock_llm(_plan_json([{"tool": "refresh_feeds", "article_id": None}]))
    with (
        patch("openai.OpenAI", return_value=client),
        patch("news_dashboard.ingest.service.ingest_all") as mock_ingest,
    ):
        mock_ingest.return_value = MagicMock(results={})
        result = plan_actions("refresh my feeds", user_id=user_id, is_admin=True)
    assert result["actionable"] is True
    mock_ingest.assert_not_called()  # not executed until approved


def test_plan_actions_rejects_malformed_args(db: str) -> None:
    user_id = _make_user(db, "alice")
    _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "archive_article", "article_id": "not-an-int"}]))
    with patch("openai.OpenAI", return_value=client), pytest.raises(AgentActionError):
        plan_actions("archive it", user_id=user_id)


def test_plan_actions_rejects_malformed_json(db: str) -> None:
    user_id = _make_user(db, "alice")
    _insert_article(db)
    client = _mock_llm("not json at all")
    with patch("openai.OpenAI", return_value=client), pytest.raises(AgentActionError):
        plan_actions("archive it", user_id=user_id)


# ── approve_run / cancel_run ──────────────────────────────────────────────────


def test_approve_run_executes_allowlisted_mutation(db: str) -> None:
    user_id = _make_user(db, "alice")
    article_id = _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "archive_article", "article_id": article_id}]))
    with patch("openai.OpenAI", return_value=client):
        plan = plan_actions("archive it", user_id=user_id)

    run = approve_run(plan["run_id"], user_id=user_id)
    assert run["status"] == "executed"
    assert run["steps"][0]["status"] == "executed"
    assert _uas_state(db, user_id, article_id) == "archived"


def test_approve_run_owner_only(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "archive_article", "article_id": article_id}]))
    with patch("openai.OpenAI", return_value=client):
        plan = plan_actions("archive it", user_id=alice)

    with pytest.raises(AgentActionNotFoundError):
        approve_run(plan["run_id"], user_id=bob)


def test_cancel_run_records_cancelled_without_mutating(db: str) -> None:
    user_id = _make_user(db, "alice")
    article_id = _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "archive_article", "article_id": article_id}]))
    with patch("openai.OpenAI", return_value=client):
        plan = plan_actions("archive it", user_id=user_id)

    run = cancel_run(plan["run_id"], user_id=user_id)
    assert run["status"] == "cancelled"
    assert _uas_state(db, user_id, article_id) == "today"

    with pytest.raises(AgentActionError):
        approve_run(plan["run_id"], user_id=user_id)


def test_approve_run_partial_failure_marks_run_failed(db: str) -> None:
    """The second step (skipping an already-starred article) is a disallowed
    transition, so it fails while the first (independent) step still executes."""
    user_id = _make_user(db, "alice")
    article_id = _insert_article(db)
    client = _mock_llm(
        _plan_json(
            [
                {"tool": "star_article", "article_id": article_id},
                {"tool": "skip_article", "article_id": article_id},
            ]
        )
    )
    with patch("openai.OpenAI", return_value=client):
        plan = plan_actions("star then skip it", user_id=user_id)

    run = approve_run(plan["run_id"], user_id=user_id)
    assert run["status"] == "failed"
    assert run["steps"][0]["status"] == "executed"
    assert run["steps"][1]["status"] == "failed"
    assert _uas_state(db, user_id, article_id) == "today"


def test_get_run_not_found_for_other_user(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "archive_article", "article_id": article_id}]))
    with patch("openai.OpenAI", return_value=client):
        plan = plan_actions("archive it", user_id=alice)

    with pytest.raises(AgentActionNotFoundError):
        get_run(plan["run_id"], user_id=bob)


# ── API endpoints ─────────────────────────────────────────────────────────────


def test_agent_actions_api_plan_approve_flow(db: str) -> None:
    user_id = _make_user(db, "alice")
    article_id = _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "star_article", "article_id": article_id}]))

    http = TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    try:
        with patch("openai.OpenAI", return_value=client):
            plan_response = http.post("/api/agent/actions/plan", json={"query": "star it"})
        assert plan_response.status_code == 200
        run_id = plan_response.json()["run_id"]

        approve_response = http.post(f"/api/agent/actions/{run_id}/approve")
        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "executed"

        get_response = http.get(f"/api/agent/actions/{run_id}")
        assert get_response.status_code == 200
        assert get_response.json()["status"] == "executed"
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_agent_actions_api_cancel(db: str) -> None:
    user_id = _make_user(db, "alice")
    article_id = _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "star_article", "article_id": article_id}]))

    http = TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    try:
        with patch("openai.OpenAI", return_value=client):
            plan_response = http.post("/api/agent/actions/plan", json={"query": "star it"})
        run_id = plan_response.json()["run_id"]

        cancel_response = http.post(f"/api/agent/actions/{run_id}/cancel")
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_agent_actions_api_rejects_other_users_run(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    client = _mock_llm(_plan_json([{"tool": "star_article", "article_id": article_id}]))

    http = TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides[require_auth] = lambda: {
        "id": alice,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    with patch("openai.OpenAI", return_value=client):
        plan_response = http.post("/api/agent/actions/plan", json={"query": "star it"})
    run_id = plan_response.json()["run_id"]

    app.dependency_overrides[require_auth] = lambda: {
        "id": bob,
        "username": "bob",
        "email": None,
        "is_admin": False,
    }
    try:
        response = http.post(f"/api/agent/actions/{run_id}/approve")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(require_auth, None)
