"""Keep every Ruff hook on the installed, locked tool without weakening its scope."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_ruff_hooks_use_the_project_environment() -> None:
    repos = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())["repos"]
    hooks = {
        hook["id"]: hook
        for repo in repos
        for hook in repo["hooks"]
        if hook["id"].startswith("ruff")
    }
    assert set(hooks) == {"ruff", "ruff-format", "ruff-push", "ruff-format-push"}  # noqa: S101
    for repo in repos:
        if any(hook["id"] in hooks for hook in repo["hooks"]):
            assert repo["repo"] == "local"  # noqa: S101
    for name, command in (
        ("ruff", "check"),
        ("ruff-format", "format"),
        ("ruff-push", "check backend scripts"),
        ("ruff-format-push", "format --check backend scripts"),
    ):
        assert hooks[name]["entry"] == f".venv/bin/ruff {command}"  # noqa: S101
        assert hooks[name]["language"] == "system"  # noqa: S101
    assert hooks["ruff"]["args"] == ["--fix"]  # noqa: S101
    for name in ("ruff", "ruff-format"):
        assert hooks[name]["types_or"] == ["python", "pyi", "jupyter"]  # noqa: S101
        assert hooks[name]["require_serial"] is True  # noqa: S101
        assert hooks[name].get("pass_filenames", True) is True  # noqa: S101
    for name in ("ruff-push", "ruff-format-push"):
        assert hooks[name]["pass_filenames"] is False  # noqa: S101
        assert hooks[name]["stages"] == ["pre-push"]  # noqa: S101
