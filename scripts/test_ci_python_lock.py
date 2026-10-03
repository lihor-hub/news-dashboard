"""Guard against CI resolving a Python dependency graph different from uv.lock."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_uses_the_locked_python_dependency_graph() -> None:
    workflow = CI_WORKFLOW.read_text()

    assert "astral-sh/setup-uv@" in workflow  # noqa: S101
    assert "uv sync --frozen --all-extras" in workflow  # noqa: S101
    assert 'echo "$PWD/.venv/bin" >> "$GITHUB_PATH"' in workflow  # noqa: S101
    assert "pip install -e '.[dev]'" not in workflow  # noqa: S101


def test_python_lock_changes_select_backend_tests() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    steps = workflow["jobs"]["detect-changes"]["steps"]
    filter_step = next(step for step in steps if step.get("id") == "filter")
    filters = yaml.safe_load(filter_step["with"]["filters"])

    assert "uv.lock" in filters["backend"]  # noqa: S101
