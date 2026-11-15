"""Keep the Python quality gates scoped to application code and repo scripts."""

import re
import tomllib
from pathlib import Path

import yaml

from manifest_values import mapping_at, sequence_at

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["backend", "scripts"]
IMPORT_PATHS = ["backend", "backend/tests", "scripts"]
COMMANDS = [
    "ruff check backend scripts",
    "ruff format --check backend scripts",
    "mypy backend scripts",
    "ty check backend scripts",
    "pyrefly check backend scripts",
]


def test_checker_configs_share_sources_and_import_paths() -> None:
    tools = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]
    assert tools["ruff"]["src"] == SOURCES  # noqa: S101
    assert tools["mypy"]["files"] == SOURCES  # noqa: S101
    assert tools["mypy"]["mypy_path"] == IMPORT_PATHS  # noqa: S101
    assert tools["ty"]["src"]["include"] == SOURCES  # noqa: S101
    assert tools["ty"]["environment"]["extra-paths"] == IMPORT_PATHS  # noqa: S101
    assert tools["pyrefly"]["project-includes"] == SOURCES  # noqa: S101
    assert tools["pyrefly"]["search-path"] == IMPORT_PATHS  # noqa: S101


def test_make_and_ci_check_both_source_trees() -> None:
    makefile = (ROOT / "Makefile").read_text()
    workflow: object = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    ci_commands = [
        mapping_at(step).get("run") for step in sequence_at(workflow, "jobs", "lint", "steps")
    ]
    for command in COMMANDS:
        assert f"\t{command}\n" in makefile  # noqa: S101
        assert command in ci_commands  # noqa: S101
    assert "\truff check backend scripts --fix\n" in makefile  # noqa: S101
    assert "\truff format backend scripts\n" in makefile  # noqa: S101
    delivery = next(
        mapping_at(step)
        for step in sequence_at(workflow, "jobs", "lint", "steps")
        if mapping_at(step).get("name") == "Delivery regression tests"
    )
    assert "if" not in delivery  # noqa: S101
    invocation = delivery["run"]
    assert isinstance(invocation, str)  # noqa: S101
    assert "scripts/test_python_quality_scope.py" in invocation.split()  # noqa: S101
    assert "scripts/test_ruff_hooks.py" in invocation.split()  # noqa: S101


def test_type_hooks_use_locked_tools_with_matching_scopes() -> None:
    configuration: object = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    local = next(
        mapping_at(repo)
        for repo in sequence_at(configuration, "repos")
        if mapping_at(repo).get("repo") == "local"
    )
    hooks = {mapping_at(hook)["id"]: mapping_at(hook) for hook in sequence_at(local, "hooks")}
    for hook_id, command in zip(["mypy", "ty", "pyrefly"], COMMANDS[2:], strict=True):
        push = hooks[f"{hook_id}-push"]
        assert push["entry"] == f".venv/bin/{command}"  # noqa: S101
        assert push["stages"] == ["pre-push"]  # noqa: S101
        assert push["pass_filenames"] is False  # noqa: S101
        assert hooks[hook_id]["entry"] == f".venv/bin/{command}"  # noqa: S101
        assert hooks[hook_id]["pass_filenames"] is False  # noqa: S101
        for hook in (hooks[hook_id], push):
            assert hook["types"] == ["file"]  # noqa: S101
            pattern = hook["files"]
            assert isinstance(pattern, str)  # noqa: S101
            for filename in (
                "backend/tests/conftest.py",
                "scripts/verify-deployed-build.py",
                "scripts/helper.pyi",
                "pyproject.toml",
                "uv.lock",
                ".pre-commit-config.yaml",
            ):
                assert re.search(pattern, filename), filename  # noqa: S101
            for filename in ("README.md", "package.json", "nested/pyproject.toml", "uv.lock.old"):
                assert not re.search(pattern, filename), filename  # noqa: S101
