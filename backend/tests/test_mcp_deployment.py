"""Repository-level contract for the real application-container MCP smoke."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = ROOT / "scripts" / "smoke-mcp-container.sh"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.mark.parametrize("failure", [False, True])
def test_container_token_helper_closes_pool_before_interpreter_shutdown(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    from news_dashboard import auth, db
    from news_dashboard.mcp import service

    closed: list[bool] = []
    monkeypatch.setattr(auth, "get_user_by_username", lambda _: {"id": 1})
    monkeypatch.setattr(db, "close_connection_pool", lambda: closed.append(True))

    def create_token(*_args: object, **_kwargs: object) -> dict[str, str]:
        if failure:
            message = "token creation failed"
            raise RuntimeError(message)
        return {"token": "test-only-token"}

    monkeypatch.setattr(service, "create_token", create_token)
    prefix = """smoke_token="$(docker exec "${app_name}" python -c '"""
    helper = SMOKE_SCRIPT.read_text(encoding="utf-8").split(prefix, 1)[1].split("\n')\"", 1)[0]
    with pytest.raises(RuntimeError, match="token creation failed") if failure else nullcontext():
        # Execute the repository-owned helper, with its DB boundaries replaced.
        exec(compile(helper, "<container-token-helper>", "exec"), {})  # noqa: S102
    assert closed == [True]


def test_container_smoke_uses_supported_image_and_keeps_database_private() -> None:
    script = SMOKE_SCRIPT.read_text()

    assert "docker build" in script
    assert '"${image_name}"' in script
    assert "pgvector/pgvector:pg16" in script
    assert 'docker port "${postgres_name}" 5432/tcp' in script
    assert "-p 5432:5432" not in script
    assert "-p 127.0.0.1::8080" in script


def test_container_smoke_probes_mounted_transport_and_never_echoes_bearer() -> None:
    script = SMOKE_SCRIPT.read_text()

    for required in (
        "StreamableHttpTransport",
        "/mcp/",
        "list_tools",
        "list_latest_news",
        "<!doctype html",
        "MCP_SERVER_ENABLED",
        "attacker.example",
        "MCP_SMOKE_TOKEN",
    ):
        assert required in script
    assert 'echo "${smoke_token}"' not in script
    assert "Authorization: Bearer ${smoke_token}" not in script
    assert "set -x" not in script


def test_ci_runs_container_smoke_without_printing_environment() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    job = workflow["jobs"]["mcp-container-smoke"]
    steps = job["steps"]
    rollup = workflow["jobs"]["test"]

    assert job["timeout-minutes"] == 20
    assert "merge_group" in job["if"]
    assert any(step.get("run") == "uv sync --frozen --all-extras" for step in steps)
    assert any(step.get("run") == 'echo "$PWD/.venv/bin" >> "$GITHUB_PATH"' for step in steps)
    assert any(step.get("run") == "scripts/smoke-mcp-container.sh" for step in steps)
    assert all("printenv" not in step.get("run", "") for step in steps)
    assert "mcp-container-smoke" in rollup["needs"]
    assert "needs.mcp-container-smoke.result" in rollup["steps"][0]["run"]
