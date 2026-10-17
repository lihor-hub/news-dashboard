"""Guard against CI resolving a Python dependency graph different from uv.lock."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.mark.parametrize("filename", ["ci.yml", "nightly.yml", "pr-timing.yml"])
def test_application_jobs_use_final_python315(filename: str) -> None:
    workflow = yaml.safe_load((CI_WORKFLOW.parent / filename).read_text(encoding="utf-8"))
    declarations = [
        step["with"]["python-version"]
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert declarations == ["3.15"] * (4 if filename == "ci.yml" else 1)  # noqa: S101


def test_manual_full_suite_uses_boolean_inputs() -> None:
    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    for name in ("test-backend", "test-frontend", "desktop", "test-a11y"):
        condition = jobs[name]["if"]
        assert "inputs.full_suite" in condition  # noqa: S101
        assert "inputs.full_suite == 'true'" not in condition  # noqa: S101


def test_frozen_all_extras_jobs_install_native_headers_before_sync() -> None:
    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    for name in ("lint", "smoke", "mcp-container-smoke", "test-backend"):
        steps = jobs[name]["steps"]
        sync = next(
            i for i, step in enumerate(steps) if step.get("run") == "uv sync --frozen --all-extras"
        )
        prerequisites = "\n".join(step.get("run", "") for step in steps[:sync])
        for package in (
            "build-essential",
            "libffi-dev",
            "libxml2-dev",
            "libxslt1-dev",
            "zlib1g-dev",
        ):
            assert package in prerequisites  # noqa: S101


def test_release_helpers_keep_system_python_and_compatible_grammar() -> None:
    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    publish = jobs["publish"]
    assert not any(  # noqa: S101
        step.get("uses", "").startswith("actions/setup-python@") for step in publish["steps"]
    )
    for filename in ("bump_version.py", "humanize_commits.py", "update_changelog.py"):
        source = (ROOT / "scripts" / filename).read_text(encoding="utf-8")
        ast.parse(source, feature_version=(3, 10))
    assert "python3 scripts/update_changelog.py" in CI_WORKFLOW.read_text()  # noqa: S101


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
